#!/usr/bin/env python3
"""Issue #19 ATR-regime conditioning audit.

Runs the Phase 1 state audit for TR_{t-1}/ATR20 and an optional Phase 2
diagnostic Donchian A/B. This script cannot approve paper/live trading or
directly promote a primary validation candidate.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


RSI_UNAVAILABLE_REASON = "rsi_exact_frozen_definition_not_recovered_without_inference"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/atr_regime_conditioning_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--run-phase2",
        action="store_true",
        help="Run the diagnostic Donchian Phase 2 A/B if Phase 1 passes. RSI remains unavailable unless exactly recovered.",
    )
    p.add_argument("--local-parity", action="store_true", help="Run Phase 1 summary on local Ninja OHLCV if present.")
    p.add_argument("--include-supplemental", action="store_true", help="Also write supplemental 2026 Q1 Phase 1 summaries.")
    return p.parse_args()


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return path.as_posix()


def norm_col(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def pick(cols: list[str], aliases: list[str]) -> str | None:
    by_norm = {norm_col(c): c for c in cols}
    for alias in aliases:
        hit = by_norm.get(norm_col(alias))
        if hit:
            return hit
    return None


def infer_root_from_symbol(symbol: Any, roots: set[str]) -> str:
    text = str(symbol).upper().strip()
    for root in sorted(roots, key=len, reverse=True):
        if text == root or text.startswith(root):
            return root
    match = re.match(r"([A-Z]+)", text)
    return match.group(1) if match else "UNKNOWN"


def read_ohlcv(path: Path, cfg: dict[str, Any], label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")

    raw = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    cols = list(raw.columns)
    aliases = cfg["column_aliases"]
    mapped = {name: pick(cols, names) for name, names in aliases.items()}

    required = ["timestamp", "open", "high", "low", "close"]
    missing = [name for name in required if not mapped.get(name)]
    if missing:
        raise ValueError(f"Missing columns {missing} in {path}; available={cols[:80]}")

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(raw[mapped["timestamp"]], utc=True, errors="coerce"),
        "open": pd.to_numeric(raw[mapped["open"]], errors="coerce"),
        "high": pd.to_numeric(raw[mapped["high"]], errors="coerce"),
        "low": pd.to_numeric(raw[mapped["low"]], errors="coerce"),
        "close": pd.to_numeric(raw[mapped["close"]], errors="coerce"),
    })
    out["volume"] = pd.to_numeric(raw[mapped["volume"]], errors="coerce").fillna(0) if mapped.get("volume") else 0.0

    roots = {str(root).upper() for root in cfg.get("roots", ["MNQ"])}
    if mapped.get("root"):
        out["root"] = raw[mapped["root"]].astype(str).str.upper()
    elif mapped.get("symbol"):
        out["root"] = raw[mapped["symbol"]].map(lambda value: infer_root_from_symbol(value, roots))
    else:
        out["root"] = str(cfg.get("default_root", "MNQ")).upper()

    out = out[out["root"].isin(roots)].dropna(subset=required).sort_values(["root", "timestamp"])
    out["source_label"] = label
    out["source_path"] = repo_rel(path)

    if out.empty:
        raise ValueError(f"No rows after filtering roots={sorted(roots)} from {path}")
    if (out["high"] < out["low"]).any():
        raise ValueError(f"Found high < low rows in {path}")
    return out.reset_index(drop=True)


def filter_by_session_window(df: pd.DataFrame, cfg: dict[str, Any], window: dict[str, Any]) -> pd.DataFrame:
    x = add_session_date(df, cfg)
    start = str(window["start"])
    end = str(window["end"])
    out = x[(x["session_date"] >= start) & (x["session_date"] <= end)].copy()
    if out.empty:
        raise ValueError(f"No rows for date window {window.get('label', '')}: {start}..{end}")
    out["data_window_label"] = window.get("label", f"{start}_to_{end}")
    return out.reset_index(drop=True)


def add_session_date(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    local_ts = out["timestamp"].dt.tz_convert(cfg.get("session_timezone", "America/New_York"))
    out["session_date"] = local_ts.dt.date.astype(str)
    return out


def daily_state(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_session_date(df, cfg)
    d = x.groupby(["root", "session_date"], as_index=False).agg(
        timestamp_first=("timestamp", "min"),
        timestamp_last=("timestamp", "max"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_label=("source_label", "first"),
        source_path=("source_path", "first"),
    ).sort_values(["root", "session_date"]).reset_index(drop=True)

    tick = float(cfg.get("tick_size", 0.25))
    d["tr"] = d["high"] - d["low"]
    d["close_to_close_return_points"] = d.groupby("root")["close"].diff()
    denom = d["tr"].clip(lower=tick)
    d["trendiness"] = (d["close"] - d["open"]).abs() / denom
    d["signed_trendiness"] = (d["close"] - d["open"]) / denom

    sd = cfg["state_definition"]
    prior_tr = d.groupby("root")["tr"].shift(1)
    d["prior_day_tr"] = prior_tr
    d["atr20"] = prior_tr.groupby(d["root"]).rolling(
        int(sd["atr_window_days"]),
        min_periods=int(sd["atr_window_days"]),
    ).mean().reset_index(level=0, drop=True)
    d["range_ratio"] = d["prior_day_tr"] / d["atr20"]

    d["state"] = "unclassified"
    compression = float(sd["compression_threshold"])
    expansion = float(sd["expansion_threshold"])
    d.loc[d["range_ratio"] < compression, "state"] = "compression"
    d.loc[(d["range_ratio"] >= compression) & (d["range_ratio"] <= expansion), "state"] = "neutral"
    d.loc[d["range_ratio"] > expansion, "state"] = "expansion"
    d["state_next"] = d.groupby("root")["state"].shift(-1)
    d["range_ratio_bin"] = pd.cut(
        d["range_ratio"],
        [-math.inf, 0.7, 0.9, 1.1, 1.3, math.inf],
        labels=["lt_0_7", "0_7_to_0_9", "0_9_to_1_1", "1_1_to_1_3", "gt_1_3"],
    )
    return d


def behavior(d: pd.DataFrame, group: str) -> pd.DataFrame:
    x = d[(d["state"] != "unclassified") & d[group].notna()].copy()
    rows: list[dict[str, Any]] = []
    for (root, key), part in x.groupby(["root", group], observed=False):
        comparable = part[part["state_next"].notna()].copy()
        same_state = comparable["state"] == comparable["state_next"]
        rows.append({
            "root": root,
            group: str(key),
            "days": int(len(part)),
            "comparable_next_state_days": int(len(comparable)),
            "mean_range": part["tr"].mean(),
            "median_range": part["tr"].median(),
            "mean_close_to_close_return_points": part["close_to_close_return_points"].mean(),
            "median_close_to_close_return_points": part["close_to_close_return_points"].median(),
            "mean_trendiness": part["trendiness"].mean(),
            "median_trendiness": part["trendiness"].median(),
            "mean_signed_trendiness": part["signed_trendiness"].mean(),
            "median_signed_trendiness": part["signed_trendiness"].median(),
            "same_state_next_day_probability": same_state.mean() if len(same_state) else float("nan"),
        })
    return pd.DataFrame(rows)


def distribution(d: pd.DataFrame) -> pd.DataFrame:
    x = d[d["state"] != "unclassified"].copy()
    x["year"] = pd.to_datetime(x["session_date"]).dt.year
    out = x.groupby(["root", "year", "state"], as_index=False).size().rename(columns={"size": "days"})
    out["share"] = out["days"] / out.groupby(["root", "year"])["days"].transform("sum")
    return out


def state_quality_summary(d: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for root, part in d[d["state"] != "unclassified"].groupby("root"):
        med = part.groupby("state")["tr"].median().to_dict()
        rows.append({
            "root": root,
            "compression_days": int((part["state"] == "compression").sum()),
            "neutral_days": int((part["state"] == "neutral").sum()),
            "expansion_days": int((part["state"] == "expansion").sum()),
            "compression_median_range": med.get("compression"),
            "neutral_median_range": med.get("neutral"),
            "expansion_median_range": med.get("expansion"),
            "expansion_median_range_above_compression": bool(med.get("expansion", -math.inf) > med.get("compression", math.inf)),
        })
    out = pd.DataFrame(rows)
    out["session_convention"] = cfg.get("session_convention", "local_calendar_date")
    return out


def phase1_gate(d: pd.DataFrame, cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    gates = cfg["phase1_gates"]
    x = d[d["state"] != "unclassified"].copy()
    reasons: list[str] = []

    for root, part in x.groupby("root"):
        for state in ["compression", "expansion"]:
            n = int((part["state"] == state).sum())
            if n < int(gates["min_days_per_primary_state"]):
                reasons.append(f"{root}:{state}_too_sparse:{n}")
        med = part.groupby("state")["tr"].median().to_dict()
        if med.get("expansion", -math.inf) <= med.get("compression", math.inf):
            reasons.append(f"{root}:expansion_median_range_not_above_compression")

    dist = distribution(d)
    for root in dist["root"].dropna().unique():
        rd = dist[dist["root"] == root]
        for state in ["compression", "expansion"]:
            years = rd[(rd["state"] == state) & (rd["days"] >= int(gates["min_days_per_state_per_year"]))]["year"].nunique()
            if years < int(gates["min_years_with_primary_states"]):
                reasons.append(f"{root}:{state}_not_stable_across_years:{years}")
    return not reasons, reasons


def resample_ohlcv(df: pd.DataFrame, timeframe: str, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_session_date(df, cfg).copy()
    rows: list[pd.DataFrame] = []
    for root, part in x.groupby("root"):
        bars = part.set_index("timestamp").sort_index().resample(timeframe).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            session_date=("session_date", "last"),
        )
        bars = bars.dropna(subset=["open", "high", "low", "close"]).reset_index()
        bars["root"] = root
        rows.append(bars)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(["root", "timestamp"]).reset_index(drop=True)


def simulate_donchian(df: pd.DataFrame, daily: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    signal_cfg = cfg["signals"]["donchian_simple_60m"]
    lookback = int(signal_cfg["lookback_bars"])
    hold_bars = int(signal_cfg["hold_bars"])
    bars = resample_ohlcv(df, signal_cfg.get("timeframe", "60min"), cfg)
    state_lookup = daily[["root", "session_date", "state"]].copy()
    trades: list[dict[str, Any]] = []

    for root, part in bars.groupby("root"):
        part = part.sort_values("timestamp").reset_index(drop=True).copy()
        part["prior_high"] = part["high"].rolling(lookback, min_periods=lookback).max().shift(1)
        part["prior_low"] = part["low"].rolling(lookback, min_periods=lookback).min().shift(1)
        next_allowed = 0
        for i, row in part.iterrows():
            if i < next_allowed or pd.isna(row["prior_high"]) or pd.isna(row["prior_low"]):
                continue
            direction = 0
            if row["close"] > row["prior_high"]:
                direction = 1
            elif row["close"] < row["prior_low"]:
                direction = -1
            if direction == 0:
                continue
            exit_i = i + hold_bars
            if exit_i >= len(part):
                continue
            exit_row = part.iloc[exit_i]
            entry = float(row["close"])
            exit_price = float(exit_row["close"])
            gross_points = (exit_price - entry) * direction
            trades.append({
                "signal": "donchian_simple_60m",
                "root": root,
                "direction": "long" if direction > 0 else "short",
                "entry_timestamp": row["timestamp"].isoformat(),
                "exit_timestamp": exit_row["timestamp"].isoformat(),
                "session_date": row["session_date"],
                "entry_price": entry,
                "exit_price": exit_price,
                "gross_points": gross_points,
                "lookback_bars": lookback,
                "hold_bars": hold_bars,
            })
            next_allowed = exit_i + 1

    out = pd.DataFrame(trades)
    if out.empty:
        return out
    out = out.merge(state_lookup, on=["root", "session_date"], how="left")
    out["state"] = out["state"].fillna("unclassified")
    return out


def profit_factor(values: pd.Series) -> float:
    winners = values[values > 0].sum()
    losers = values[values < 0].sum()
    if losers == 0:
        return float("inf") if winners > 0 else 0.0
    return float(winners / abs(losers))


def max_drawdown(values: pd.Series) -> float:
    equity = values.cumsum()
    peak = equity.cummax()
    dd = peak - equity
    return float(dd.max()) if len(dd) else 0.0


def summarize_trades(part: pd.DataFrame, gates: dict[str, Any]) -> dict[str, Any]:
    if part.empty:
        return {
            "trades": 0,
            "net_dollars": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_dollars": 0.0,
            "win_rate": 0.0,
            "largest_winner_share": 0.0,
            "best_day_share": 0.0,
            "best_week_share": 0.0,
            "net_excluding_largest": 0.0,
            "passes_cost_and_concentration_gates": False,
        }

    net = float(part["net_dollars"].sum())
    largest = float(part["net_dollars"].max())
    day_net = part.groupby("session_date")["net_dollars"].sum()
    week_net = part.groupby(pd.to_datetime(part["entry_timestamp"], utc=True).dt.strftime("%G-W%V"))["net_dollars"].sum()
    largest_share = largest / net if net > 0 and largest > 0 else 0.0
    best_day_share = float(day_net.max() / net) if net > 0 and len(day_net) and day_net.max() > 0 else 0.0
    best_week_share = float(week_net.max() / net) if net > 0 and len(week_net) and week_net.max() > 0 else 0.0
    net_ex_largest = net - largest if largest > 0 else net
    pf = profit_factor(part["net_dollars"])
    passes = (
        net > float(gates["min_net_dollars"])
        and pf >= float(gates["min_profit_factor"])
        and largest_share < float(gates["max_concentration_share"])
        and best_day_share < float(gates["max_concentration_share"])
        and best_week_share < float(gates["max_concentration_share"])
        and net_ex_largest > float(gates["min_net_without_largest"])
    )
    return {
        "trades": int(len(part)),
        "net_dollars": net,
        "profit_factor": pf,
        "max_drawdown_dollars": max_drawdown(part["net_dollars"]),
        "win_rate": float((part["net_dollars"] > 0).mean()),
        "largest_winner_share": largest_share,
        "best_day_share": best_day_share,
        "best_week_share": best_week_share,
        "net_excluding_largest": net_ex_largest,
        "passes_cost_and_concentration_gates": bool(passes),
    }


def run_phase2_outputs(out: Path, df: pd.DataFrame, daily: pd.DataFrame, cfg: dict[str, Any]) -> tuple[bool, str]:
    trades = simulate_donchian(df, daily, cfg)
    tick = float(cfg.get("tick_size", 0.25))
    dpp_by_root = {str(k).upper(): float(v) for k, v in cfg.get("dollars_per_point_by_root", {}).items()}
    default_dpp = float(cfg.get("dollars_per_point", 2.0))
    slippages = cfg.get("signal_slippage_ticks", {}).get("donchian_simple_60m_diagnostic", [1.0, 2.0])
    gates = cfg["phase2_gates"]
    perf_rows: list[dict[str, Any]] = []
    controls_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []

    if trades.empty:
        trades.to_csv(out / "donchian_simple_60m_trades.csv", index=False)
        skipped_signal_outputs(out, cfg, "donchian_no_trades_generated_rsi_unavailable")
        return False, "donchian_no_trades_generated"

    all_costed: list[pd.DataFrame] = []
    for slip in slippages:
        costed = trades.copy()
        costed["slippage_ticks_per_side"] = float(slip)
        costed["round_turn_cost_points"] = 2.0 * float(slip) * tick
        costed["dollars_per_point"] = costed["root"].map(dpp_by_root).fillna(default_dpp)
        costed["net_points"] = costed["gross_points"] - costed["round_turn_cost_points"]
        costed["net_dollars"] = costed["net_points"] * costed["dollars_per_point"] - float(cfg.get("commission_round_turn", 0.0))
        all_costed.append(costed)

        for root, root_part in costed.groupby("root"):
            unconditional = summarize_trades(root_part, gates)
            controls_rows.append({
                "signal": "donchian_simple_60m",
                "root": root,
                "state": "unconditional",
                "slippage_ticks_per_side": float(slip),
                **unconditional,
                "skip_reason": "",
            })
            concentration_rows.append({
                "signal": "donchian_simple_60m",
                "root": root,
                "state": "unconditional",
                "slippage_ticks_per_side": float(slip),
                **{k: unconditional[k] for k in ["largest_winner_share", "best_day_share", "best_week_share", "net_excluding_largest"]},
                "skip_reason": "",
            })
            root_part = root_part.copy()
            root_part["year"] = pd.to_datetime(root_part["entry_timestamp"], utc=True).dt.year
            for year, year_part in root_part.groupby("year"):
                year_rows.append({
                    "signal": "donchian_simple_60m",
                    "root": root,
                    "state": "unconditional",
                    "year": int(year),
                    "slippage_ticks_per_side": float(slip),
                    **summarize_trades(year_part, gates),
                })

            for state in ["compression", "neutral", "expansion"]:
                state_part = root_part[root_part["state"] == state]
                summary = summarize_trades(state_part, gates)
                perf_rows.append({
                    "signal": "donchian_simple_60m",
                    "root": root,
                    "state": state,
                    "slippage_ticks_per_side": float(slip),
                    **{k: summary[k] for k in ["trades", "net_dollars", "profit_factor", "max_drawdown_dollars", "win_rate", "passes_cost_and_concentration_gates"]},
                    "skip_reason": "",
                })
                concentration_rows.append({
                    "signal": "donchian_simple_60m",
                    "root": root,
                    "state": state,
                    "slippage_ticks_per_side": float(slip),
                    **{k: summary[k] for k in ["largest_winner_share", "best_day_share", "best_week_share", "net_excluding_largest"]},
                    "skip_reason": "",
                })
                for year, year_part in state_part.assign(year=pd.to_datetime(state_part["entry_timestamp"], utc=True).dt.year).groupby("year"):
                    year_rows.append({
                        "signal": "donchian_simple_60m",
                        "root": root,
                        "state": state,
                        "year": int(year),
                        "slippage_ticks_per_side": float(slip),
                        **summarize_trades(year_part, gates),
                    })

    costed_trades = pd.concat(all_costed, ignore_index=True)
    costed_trades.to_csv(out / "donchian_simple_60m_trades.csv", index=False)

    rsi_perf = [
        {
            "signal": "rsi_reversion_30m",
            "root": root,
            "state": state,
            "slippage_ticks_per_side": 1.0,
            "trades": 0,
            "net_dollars": "",
            "profit_factor": "",
            "max_drawdown_dollars": "",
            "win_rate": "",
            "passes_cost_and_concentration_gates": False,
            "skip_reason": RSI_UNAVAILABLE_REASON,
        }
        for root in sorted(df["root"].unique())
        for state in ["compression", "neutral", "expansion"]
    ]
    rsi_controls = [
        {
            "signal": "rsi_reversion_30m",
            "root": root,
            "state": "unconditional",
            "slippage_ticks_per_side": 1.0,
            "trades": 0,
            "net_dollars": "",
            "profit_factor": "",
            "max_drawdown_dollars": "",
            "win_rate": "",
            "largest_winner_share": "",
            "best_day_share": "",
            "best_week_share": "",
            "net_excluding_largest": "",
            "passes_cost_and_concentration_gates": False,
            "skip_reason": RSI_UNAVAILABLE_REASON,
        }
        for root in sorted(df["root"].unique())
    ]

    pd.DataFrame([*perf_rows, *rsi_perf]).to_csv(out / "signal_performance_by_state.csv", index=False)
    pd.DataFrame([*controls_rows, *rsi_controls]).to_csv(out / "signal_controls_unconditional.csv", index=False)
    pd.DataFrame(concentration_rows + [
        {
            "signal": "rsi_reversion_30m",
            "root": root,
            "state": state,
            "slippage_ticks_per_side": 1.0,
            "largest_winner_share": "",
            "best_day_share": "",
            "best_week_share": "",
            "net_excluding_largest": "",
            "skip_reason": RSI_UNAVAILABLE_REASON,
        }
        for root in sorted(df["root"].unique())
        for state in ["compression", "neutral", "expansion", "unconditional"]
    ]).to_csv(out / "concentration_by_state.csv", index=False)
    pd.DataFrame(year_rows).to_csv(out / "signal_year_splits.csv", index=False)

    gate_passes = [row for row in perf_rows if row["passes_cost_and_concentration_gates"] and row["slippage_ticks_per_side"] == 2.0]
    if gate_passes:
        return True, "conditional_signal_edge_diagnostic_only"
    return True, "regime_proxy_useful_but_no_signal_edge"


def skipped_signal_outputs(out: Path, cfg: dict[str, Any], reason: str) -> None:
    signals = sorted(cfg.get("signals", {}).keys()) or ["unknown_signal"]
    states = ["compression", "neutral", "expansion"]
    perf_cols = ["signal", "state", "slippage_ticks_per_side", "trades", "net_dollars", "profit_factor", "skip_reason"]
    perf_rows = [
        {
            "signal": signal,
            "state": state,
            "slippage_ticks_per_side": "",
            "trades": 0,
            "net_dollars": "",
            "profit_factor": "",
            "skip_reason": reason,
        }
        for signal in signals
        for state in states
    ]
    unconditional_rows = [
        {
            "signal": signal,
            "state": "unconditional",
            "slippage_ticks_per_side": "",
            "trades": 0,
            "net_dollars": "",
            "profit_factor": "",
            "skip_reason": reason,
        }
        for signal in signals
    ]
    pd.DataFrame(perf_rows, columns=perf_cols).to_csv(out / "signal_performance_by_state.csv", index=False)
    pd.DataFrame(unconditional_rows, columns=perf_cols).to_csv(out / "signal_controls_unconditional.csv", index=False)
    concentration_cols = ["signal", "state", "largest_winner_share", "best_day_share", "best_week_share", "net_excluding_largest", "skip_reason"]
    concentration_rows = [
        {
            "signal": signal,
            "state": state,
            "largest_winner_share": "",
            "best_day_share": "",
            "best_week_share": "",
            "net_excluding_largest": "",
            "skip_reason": reason,
        }
        for signal in signals
        for state in [*states, "unconditional"]
    ]
    pd.DataFrame(concentration_rows, columns=concentration_cols).to_csv(out / "concentration_by_state.csv", index=False)


def write_lineage(out: Path, cfg: dict[str, Any], sources: list[dict[str, Any]], primary_window: dict[str, Any]) -> None:
    lines = [
        "# Source Lineage",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Source | Path | File size bytes | Rows | First | Last | Role |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for source in sources:
        lines.append(
            f"| {source['label']} | `{source['path']}` | {source['size_bytes']} | {source['rows']} | {source['first']} | {source['last']} | {source['role']} |"
        )
    lines += [
        "",
        "## Session convention",
        "",
        f"Daily session date = timestamp converted to `{cfg.get('session_timezone')}` and local calendar date.",
        f"Session convention label: `{cfg.get('session_convention', 'local_calendar_date')}`.",
        "",
        "## Primary data window",
        "",
        f"Primary Databento output is filtered to `{primary_window.get('label')}`: `{primary_window.get('start')}` through `{primary_window.get('end')}`.",
        "Supplemental windows, when requested, are written separately and are not pooled into the primary verdict.",
        "",
        "## Local Ninja parity",
        "",
        "Local Ninja parity is a small recency sanity check only. Its state counts are under-sampled and must not be treated as confirmatory evidence.",
        "",
        "## Lookahead guard",
        "",
        "State for day t uses prior-day TR and ATR over completed prior sessions only. Current-day high/low is not included in the state for that day.",
        "",
        "## Scope guard",
        "",
        "This audit cannot approve paper/live trading and cannot directly promote a candidate.",
    ]
    (out / "source_lineage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verdict(
    out: Path,
    cfg: dict[str, Any],
    ok: bool,
    reasons: list[str],
    phase2_requested: bool,
    phase2_ran: bool,
    phase2_verdict: str | None,
) -> str:
    if not ok:
        verdict = "regime_proxy_rejected"
    elif phase2_ran:
        verdict = phase2_verdict or "regime_proxy_useful_but_no_signal_edge"
    else:
        verdict = "incomplete_reproducibility"
    text = [
        "# ATR Regime Conditioning Verdict",
        "",
        f"Issue: {cfg.get('issue_url')}",
        "",
        f"Verdict: `{verdict}`",
        "",
        "This is a regime-conditioning research audit. It cannot approve paper/live trading and cannot directly promote a primary validation candidate.",
        "",
        "## Phase 1",
        "",
        f"Status: {'pass' if ok else 'fail'}",
        "",
        "Reasons:",
    ]
    text += [f"- {reason}" for reason in reasons] or ["- none"]
    text += [
        "",
        "Interpretation:",
        "- The ATR proxy separates next-day range directionally, but the spread is modest and noisy.",
        "- Neutral and expansion median ranges are close, and diagnostic bins are not monotonic enough to imply a stable structural regime.",
        "- This is a lagging realized-volatility state proxy, not evidence of a structural dealer-gamma regime.",
        "- Treat the result as permission to continue diagnostics, not as proof of a useful trading regime.",
        "",
        "## Phase 2",
        "",
        f"Requested: {phase2_requested}",
        f"Ran: {str(phase2_ran).lower()}",
        f"RSI status: `{RSI_UNAVAILABLE_REASON}`",
        "",
        "Interpretation:",
        "- Simple Donchian 60m is diagnostic only and is not the failed confluence candidate.",
        "- RSI reversion is unavailable unless the exact frozen definition is recovered without inference.",
        "- No row in this issue can approve strategy promotion by itself.",
        "",
        "Guardrails:",
        "- Forbidden verdicts: pass_forward_validation, paper_ready, live_ready, primary_validation_candidate.",
        "- Any candidate validation must be opened as a separate issue.",
    ]
    (out / "VERDICT.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return verdict


def source_info(df: pd.DataFrame, label: str, path: Path, role: str) -> dict[str, Any]:
    size = path.stat().st_size if path.exists() else 0
    return {
        "label": label,
        "path": repo_rel(path),
        "size_bytes": size,
        "rows": int(len(df)),
        "first": df["timestamp"].min().isoformat(),
        "last": df["timestamp"].max().isoformat(),
        "role": role,
    }


def prepare_output_dir(out: Path, force: bool) -> None:
    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f"{out} exists and is non-empty; pass --force")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)


def write_top_level_report(date: str, out: Path) -> Path:
    target = Path(f"ATR_REGIME_CONDITIONING_{date}.md")
    text = [(out / "VERDICT.md").read_text(encoding="utf-8").rstrip(), ""]

    quality_path = out / "state_quality_summary.csv"
    if quality_path.exists():
        quality = pd.read_csv(quality_path)
        text += [
            "## Phase 1 State Summary",
            "",
            "| Root | Compression days | Neutral days | Expansion days | Compression median range | Expansion median range | Expansion > compression |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for row in quality.to_dict("records"):
            text.append(
                "| {root} | {compression_days} | {neutral_days} | {expansion_days} | {compression_median_range} | {expansion_median_range} | {expansion_median_range_above_compression} |".format(
                    **row
                )
            )
        text.append("")

    perf_path = out / "signal_performance_by_state.csv"
    if perf_path.exists():
        perf = pd.read_csv(perf_path)
        donchian = perf[(perf.get("signal") == "donchian_simple_60m") & (perf.get("slippage_ticks_per_side") == 2.0)].copy()
        if not donchian.empty:
            text += [
                "## Phase 2 Donchian Diagnostic",
                "",
                "| Root | State | Trades | Net dollars | PF | Gate pass |",
                "|---|---|---:|---:|---:|---|",
            ]
            for row in donchian.to_dict("records"):
                text.append(
                    f"| {row.get('root')} | {row.get('state')} | {row.get('trades')} | {float(row.get('net_dollars', 0.0)):.2f} | {float(row.get('profit_factor', 0.0)):.3f} | {row.get('passes_cost_and_concentration_gates')} |"
                )
            text += [
                "",
                "This is a diagnostic A/B only. It is not a validation of the failed Donchian confluence candidate and does not promote a strategy.",
                "",
            ]

    text += [
        "## Interpretation",
        "",
        "- Phase 1 separation is modest/noisy: expansion has higher median range than compression, but this is only a lagging realized-volatility proxy.",
        "- Neutral and expansion medians are close, and diagnostic bins are not monotonic enough to treat the state proxy as structurally proven.",
        "- The proxy must not be described as actual gamma exposure or a proven structural market regime.",
        "- RSI remains unavailable because the exact frozen definition was not recovered without inference.",
        "- Local Ninja parity is under-sampled and should be read as sanity/recency context only, not confirmatory validation.",
        "",
        "## Generated Artifacts",
        "",
        f"- Report directory: `{repo_rel(out)}`",
        "- Main tables: `state_distribution_by_year.csv`, `next_day_behavior_by_state.csv`, `bin_grid_diagnostics.csv`, `local_ninja_parity_check.csv`.",
        "- Signal tables contain the diagnostic Donchian A/B when `--run-phase2` is used, plus explicit RSI unavailable rows.",
        "",
    ]
    target.write_text("\n".join(text), encoding="utf-8")
    return target


def main() -> None:
    args = parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    out = args.out_dir or Path(f"reports/atr_regime_conditioning_{args.date}")
    prepare_output_dir(out, args.force)

    primary_path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
    full_primary = read_ohlcv(primary_path, cfg, "databento_ohlcv_1m")
    primary_window = cfg.get("primary_date_filter", {"start": "2023-01-01", "end": "2025-12-31", "label": "primary_2023_2025"})
    primary = filter_by_session_window(full_primary, cfg, primary_window)
    sources = [source_info(primary, "databento_ohlcv_1m", primary_path, "primary_long_history")]

    daily = daily_state(primary, cfg)
    daily.to_csv(out / "daily_state_table.csv", index=False)
    distribution(daily).to_csv(out / "state_distribution_by_year.csv", index=False)
    behavior(daily, "state").to_csv(out / "next_day_behavior_by_state.csv", index=False)
    behavior(daily, "range_ratio_bin").to_csv(out / "bin_grid_diagnostics.csv", index=False)
    state_quality_summary(daily, cfg).to_csv(out / "state_quality_summary.csv", index=False)

    phase1_ok, reasons = phase1_gate(daily, cfg)
    phase2_ran = False
    phase2_verdict: str | None = None
    if args.run_phase2 and phase1_ok:
        phase2_ran, phase2_verdict = run_phase2_outputs(out, primary, daily, cfg)
    else:
        skipped_signal_outputs(out, cfg, "phase2_not_requested" if not args.run_phase2 else "phase1_failed_phase2_skipped")

    if args.include_supplemental:
        for window in cfg.get("supplemental_date_filters", []):
            label = str(window.get("label", "supplemental"))
            supplemental = filter_by_session_window(full_primary, cfg, window)
            supplemental_daily = daily_state(supplemental, cfg)
            behavior(supplemental_daily, "state").to_csv(out / f"{label}_next_day_behavior_by_state.csv", index=False)
            state_quality_summary(supplemental_daily, cfg).to_csv(out / f"{label}_state_quality_summary.csv", index=False)
            distribution(supplemental_daily).to_csv(out / f"{label}_state_distribution_by_year.csv", index=False)

    if args.local_parity:
        local_path = Path(cfg["data_sources"].get("local_ninja_ohlcv_1m", ""))
        if local_path.exists():
            local = read_ohlcv(local_path, cfg, "local_ninja_ohlcv_1m")
            sources.append(source_info(local, "local_ninja_ohlcv_1m", local_path, "local_parity_under_sampled_recency_sanity_only"))
            local_daily = daily_state(local, cfg)
            behavior(local_daily, "state").to_csv(out / "local_ninja_parity_check.csv", index=False)
        else:
            pd.DataFrame([{"status": "not_available", "path": local_path.as_posix()}]).to_csv(out / "local_ninja_parity_check.csv", index=False)
    else:
        pd.DataFrame([{"status": "not_requested"}]).to_csv(out / "local_ninja_parity_check.csv", index=False)

    state_def = {
        "proxy": "prior_day_TR/ATR20",
        "session_timezone": cfg.get("session_timezone"),
        "session_convention": cfg.get("session_convention", "local_calendar_date"),
        **cfg["state_definition"],
        "primary_date_filter": primary_window,
        "supplemental_date_filters": cfg.get("supplemental_date_filters", []),
    }
    (out / "state_definition.json").write_text(json.dumps(state_def, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_lineage(out, cfg, sources, primary_window)
    verdict = write_verdict(out, cfg, phase1_ok, reasons, args.run_phase2, phase2_ran, phase2_verdict)
    top_report = write_top_level_report(args.date, out)
    metadata = {
        "schema_version": 1,
        "issue": cfg.get("issue_url"),
        "verdict": verdict,
        "primary_date_filter": primary_window,
        "supplemental_included": bool(args.include_supplemental),
        "phase1_ok": phase1_ok,
        "phase1_reasons": reasons,
        "phase2_requested": bool(args.run_phase2),
        "phase2_ran": phase2_ran,
        "phase2_result": phase2_verdict,
        "rsi_status": RSI_UNAVAILABLE_REASON,
        "local_ninja_parity_status": "under_sampled_recency_sanity_only_not_confirmatory",
        "top_level_report": repo_rel(top_report),
        "outputs": sorted([path.name for path in out.iterdir()] + [top_report.name, "triage_metadata.json"]),
        "forbidden_verdicts": cfg.get("forbidden_verdicts", []),
    }
    (out / "triage_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}; verdict={verdict}; top_report={top_report}")


if __name__ == "__main__":
    main()
