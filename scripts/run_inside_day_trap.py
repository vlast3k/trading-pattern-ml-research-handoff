#!/usr/bin/env python3
"""Issue #23 Inside Day Trap state-variable audit.

This is a Phase 1 audit only. It compares first-RTH-hour containment inside
the prior Globex range against subsequent rest-of-RTH behavior. It does not
run strategy signals and cannot approve trading.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/inside_day_trap_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--include-supplemental", action="store_true", help="Also write separated Databento 2026 Q1 output.")
    p.add_argument("--local-parity", action="store_true", help="Also write under-sampled local Ninja sanity output.")
    return p.parse_args()


def norm_col(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def pick(cols: list[str], aliases: list[str]) -> str | None:
    by_norm = {norm_col(c): c for c in cols}
    for alias in aliases:
        hit = by_norm.get(norm_col(alias))
        if hit:
            return hit
    return None


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return path.as_posix()


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
    if mapped.get("volume"):
        out["volume"] = pd.to_numeric(raw[mapped["volume"]], errors="coerce").fillna(0)
    else:
        out["volume"] = 0.0

    roots = {str(root).upper() for root in cfg.get("roots", ["MNQ"])}
    if mapped.get("root"):
        out["root"] = raw[mapped["root"]].astype(str).str.upper()
    elif mapped.get("symbol"):
        out["root"] = raw[mapped["symbol"]].map(lambda value: infer_root_from_symbol(value, roots))
    else:
        out["root"] = str(cfg.get("default_root", "MNQ")).upper()

    out = out[out["root"].isin(roots)].dropna(subset=required).copy()
    out = out.sort_values(["root", "timestamp"]).reset_index(drop=True)
    out["source_label"] = label
    out["source_path"] = repo_rel(path)
    if out.empty:
        raise ValueError(f"No rows after filtering roots={sorted(roots)} from {path}")
    if (out["high"] < out["low"]).any():
        raise ValueError(f"Found high < low rows in {path}")
    return out


def filter_by_local_session_date(df: pd.DataFrame, cfg: dict[str, Any], window: dict[str, str]) -> pd.DataFrame:
    x = add_time_columns(df, cfg)
    out = x[(x["local_date_str"] >= window["start"]) & (x["local_date_str"] <= window["end"])].copy()
    if out.empty:
        raise ValueError(f"No rows in {window.get('label', '')}: {window['start']}..{window['end']}")
    out["data_window_label"] = window.get("label", f"{window['start']}_to_{window['end']}")
    return out.reset_index(drop=True)


def parse_hhmm(value: str) -> int:
    h, m = str(value).split(":")
    return int(h) * 60 + int(m)


def add_time_columns(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    local_ts = out["timestamp"].dt.tz_convert(cfg.get("session_timezone", "America/New_York"))
    out["local_ts"] = local_ts
    out["local_date"] = local_ts.dt.date
    out["local_date_str"] = out["local_date"].astype(str)
    out["minute_of_day"] = local_ts.dt.hour * 60 + local_ts.dt.minute
    globex_start = parse_hhmm(cfg["session_windows"]["globex_start_prior_day"])
    globex_session_date = out["local_date"]
    evening = out["minute_of_day"] >= globex_start
    globex_session_date = globex_session_date.where(~evening, globex_session_date + timedelta(days=1))
    out["globex_session_date"] = globex_session_date.astype(str)
    return out


def summarize_bars(part: pd.DataFrame, prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_open": part["open"].iloc[0],
        f"{prefix}_high": part["high"].max(),
        f"{prefix}_low": part["low"].min(),
        f"{prefix}_close": part["close"].iloc[-1],
        f"{prefix}_volume": part["volume"].sum(),
        f"{prefix}_minutes": int(len(part)),
        f"{prefix}_timestamp_first": part["timestamp"].min().isoformat(),
        f"{prefix}_timestamp_last": part["timestamp"].max().isoformat(),
    }


def hlc3_vwap(part: pd.DataFrame) -> float:
    price = (part["high"] + part["low"] + part["close"]) / 3.0
    volume = part["volume"].clip(lower=0)
    total_volume = volume.sum()
    if total_volume > 0:
        return float((price * volume).sum() / total_volume)
    return float(price.mean())


def rotation_count(close: pd.Series) -> tuple[int, int]:
    diff = close.diff().dropna()
    signs = diff[diff != 0].map(lambda value: 1 if value > 0 else -1).tolist()
    if len(signs) < 2:
        return 0, len(signs)
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b), len(signs)


def build_session_table(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_time_columns(df, cfg)
    windows = cfg["session_windows"]
    globex_start = parse_hhmm(windows["globex_start_prior_day"])
    rth_open = parse_hhmm(windows["rth_open"])
    first_end = parse_hhmm(windows["first_hour_end"])
    rth_close = parse_hhmm(windows["rth_close"])
    tick = float(cfg.get("tick_size", 0.25))

    globex_mask = (x["minute_of_day"] >= globex_start) | (x["minute_of_day"] < rth_open)
    globex_rows: list[dict[str, Any]] = []
    for (root, session_date), part in x[globex_mask].groupby(["root", "globex_session_date"]):
        row = {"root": root, "session_date": session_date}
        row.update(summarize_bars(part, "globex"))
        globex_rows.append(row)
    globex = pd.DataFrame(globex_rows)

    first_mask = (x["minute_of_day"] >= rth_open) & (x["minute_of_day"] < first_end)
    first_rows: list[dict[str, Any]] = []
    for (root, session_date), part in x[first_mask].groupby(["root", "local_date_str"]):
        row = {"root": root, "session_date": session_date}
        row.update(summarize_bars(part, "first_hour"))
        row["first_hour_vwap"] = hlc3_vwap(part)
        first_rows.append(row)
    first = pd.DataFrame(first_rows)

    rest_mask = (x["minute_of_day"] >= first_end) & (x["minute_of_day"] < rth_close)
    rest_rows: list[dict[str, Any]] = []
    for (root, session_date), part in x[rest_mask].groupby(["root", "local_date_str"]):
        row = {"root": root, "session_date": session_date}
        row.update(summarize_bars(part, "rest_rth"))
        rotations, nonzero_moves = rotation_count(part["close"])
        row["rotation_count"] = rotations
        row["nonzero_close_move_count"] = nonzero_moves
        row["chop_index"] = rotations / max(nonzero_moves - 1, 1)
        rest_rows.append(row)
    rest = pd.DataFrame(rest_rows)

    if globex.empty or first.empty or rest.empty:
        return pd.DataFrame()

    out = first.merge(globex, on=["root", "session_date"], how="inner")
    out = out.merge(rest, on=["root", "session_date"], how="inner")
    if out.empty:
        return out

    out["globex_range"] = out["globex_high"] - out["globex_low"]
    out["first_hour_range"] = out["first_hour_high"] - out["first_hour_low"]
    out["rest_rth_range"] = out["rest_rth_high"] - out["rest_rth_low"]
    out["rest_rth_range_div_first_hour_range"] = out["rest_rth_range"] / out["first_hour_range"].clip(lower=tick)
    out["rest_rth_trendiness"] = (out["rest_rth_close"] - out["rest_rth_open"]).abs() / out["rest_rth_range"].clip(lower=tick)
    out["rest_rth_signed_trendiness"] = (out["rest_rth_close"] - out["rest_rth_open"]) / out["rest_rth_range"].clip(lower=tick)

    out["trapped_state"] = (out["first_hour_high"] < out["globex_high"]) & (out["first_hour_low"] > out["globex_low"])
    out["broken_up"] = out["first_hour_high"] >= out["globex_high"]
    out["broken_down"] = out["first_hour_low"] <= out["globex_low"]
    out["broken_both"] = out["broken_up"] & out["broken_down"]
    out["state"] = out["trapped_state"].map(lambda value: "trapped" if value else "broken")
    out["sub_state"] = "trapped"
    out.loc[out["broken_up"] & ~out["broken_down"], "sub_state"] = "broken_up"
    out.loc[out["broken_down"] & ~out["broken_up"], "sub_state"] = "broken_down"
    out.loc[out["broken_both"], "sub_state"] = "broken_both"

    boundary_fraction = float(cfg["state_definition"]["near_boundary_threshold_fraction_of_globex_range"])
    near_distance = pd.concat([
        (out["globex_high"] - out["first_hour_high"]).abs(),
        (out["first_hour_low"] - out["globex_low"]).abs(),
    ], axis=1).min(axis=1)
    out["near_boundary_but_not_broken"] = out["trapped_state"] & (
        near_distance <= out["globex_range"].clip(lower=tick) * boundary_fraction
    )

    out["new_rth_high_after_10_30"] = out["rest_rth_high"] > out["first_hour_high"]
    out["new_rth_low_after_10_30"] = out["rest_rth_low"] < out["first_hour_low"]
    out["new_rth_high_or_low_after_10_30"] = out["new_rth_high_after_10_30"] | out["new_rth_low_after_10_30"]
    known_session_high = out[["globex_high", "first_hour_high"]].max(axis=1)
    known_session_low = out[["globex_low", "first_hour_low"]].min(axis=1)
    out["new_session_high_after_10_30"] = out["rest_rth_high"] > known_session_high
    out["new_session_low_after_10_30"] = out["rest_rth_low"] < known_session_low
    out["new_session_high_or_low_after_10_30"] = out["new_session_high_after_10_30"] | out["new_session_low_after_10_30"]

    rth_high = out[["first_hour_high", "rest_rth_high"]].max(axis=1)
    rth_low = out[["first_hour_low", "rest_rth_low"]].min(axis=1)
    out["close_location_within_rth_range"] = (out["rest_rth_close"] - rth_low) / (rth_high - rth_low).clip(lower=tick)
    return out.sort_values(["root", "session_date"]).reset_index(drop=True)


def add_rest_vwap_cross_counts(session: pd.DataFrame, bars: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_time_columns(bars, cfg)
    first_end = parse_hhmm(cfg["session_windows"]["first_hour_end"])
    rth_close = parse_hhmm(cfg["session_windows"]["rth_close"])
    rest = x[(x["minute_of_day"] >= first_end) & (x["minute_of_day"] < rth_close)].copy()
    keys = session[["root", "session_date", "first_hour_vwap"]]
    rest = rest.merge(keys, left_on=["root", "local_date_str"], right_on=["root", "session_date"], how="inner")
    rest["first_hour_vwap_cross"] = (rest["low"] <= rest["first_hour_vwap"]) & (rest["high"] >= rest["first_hour_vwap"])
    crosses = rest.groupby(["root", "session_date"], as_index=False).agg(
        first_hour_vwap_cross_count=("first_hour_vwap_cross", "sum"),
        first_hour_vwap_cross_rate=("first_hour_vwap_cross", "mean"),
    )
    out = session.merge(crosses, on=["root", "session_date"], how="left")
    out["first_hour_vwap_cross_count"] = out["first_hour_vwap_cross_count"].fillna(0).astype(int)
    out["first_hour_vwap_cross_rate"] = out["first_hour_vwap_cross_rate"].fillna(0.0)
    return out


def with_unconditional(session: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([session, session.assign(state="unconditional", sub_state="unconditional")], ignore_index=True)


def summarize_state(session: pd.DataFrame) -> pd.DataFrame:
    x = with_unconditional(session)
    return x.groupby(["root", "state"], as_index=False).agg(
        days=("session_date", "nunique"),
        median_globex_range=("globex_range", "median"),
        median_first_hour_range=("first_hour_range", "median"),
        median_first_hour_div_globex_range=("first_hour_range", lambda s: (s / x.loc[s.index, "globex_range"].clip(lower=0.25)).median()),
        near_boundary_rate=("near_boundary_but_not_broken", "mean"),
        median_rest_rth_range=("rest_rth_range", "median"),
    )


def summarize_outcomes(session: pd.DataFrame, group_col: str = "state") -> pd.DataFrame:
    x = pd.concat([session, session.assign(**{group_col: "unconditional"})], ignore_index=True)
    rows: list[dict[str, Any]] = []
    for (root, state), part in x.groupby(["root", group_col], observed=False):
        rows.append({
            "root": root,
            group_col: state,
            "days": int(part["session_date"].nunique()),
            "median_rest_rth_range": part["rest_rth_range"].median(),
            "median_rest_rth_range_div_first_hour_range": part["rest_rth_range_div_first_hour_range"].median(),
            "mean_rest_rth_trendiness": part["rest_rth_trendiness"].mean(),
            "mean_rest_rth_signed_trendiness": part["rest_rth_signed_trendiness"].mean(),
            "new_rth_high_after_10_30_rate": part["new_rth_high_after_10_30"].mean(),
            "new_rth_low_after_10_30_rate": part["new_rth_low_after_10_30"].mean(),
            "new_rth_high_or_low_after_10_30_rate": part["new_rth_high_or_low_after_10_30"].mean(),
            "new_session_high_or_low_after_10_30_rate": part["new_session_high_or_low_after_10_30"].mean(),
            "mean_rotation_count": part["rotation_count"].mean(),
            "mean_chop_index": part["chop_index"].mean(),
            "mean_first_hour_vwap_cross_count": part["first_hour_vwap_cross_count"].mean(),
            "mean_first_hour_vwap_cross_rate": part["first_hour_vwap_cross_rate"].mean(),
            "median_close_location_within_rth_range": part["close_location_within_rth_range"].median(),
        })
    return pd.DataFrame(rows)


def new_high_low_metrics(session: pd.DataFrame) -> pd.DataFrame:
    return summarize_outcomes(session)[[
        "root",
        "state",
        "days",
        "new_rth_high_after_10_30_rate",
        "new_rth_low_after_10_30_rate",
        "new_rth_high_or_low_after_10_30_rate",
        "new_session_high_or_low_after_10_30_rate",
    ]]


def chop_rotation_metrics(session: pd.DataFrame) -> pd.DataFrame:
    return summarize_outcomes(session)[[
        "root",
        "state",
        "days",
        "mean_rotation_count",
        "mean_chop_index",
        "mean_first_hour_vwap_cross_count",
        "mean_first_hour_vwap_cross_rate",
    ]]


def year_splits(session: pd.DataFrame) -> pd.DataFrame:
    x = session.copy()
    x["year"] = pd.to_datetime(x["session_date"]).dt.year
    rows: list[pd.DataFrame] = []
    for _, part in x.groupby("year"):
        y = summarize_outcomes(part)
        y["year"] = int(part["year"].iloc[0])
        rows.append(y)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def concentration_or_stability(session: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    gates = cfg["phase1_gates"]
    x = session.copy()
    x["year"] = pd.to_datetime(x["session_date"]).dt.year
    x["month"] = pd.to_datetime(x["session_date"]).dt.to_period("M").astype(str)
    x["week"] = pd.to_datetime(x["session_date"]).dt.strftime("%G-W%V")
    base = summarize_outcomes(session)
    rows: list[dict[str, Any]] = []
    for root, part in x.groupby("root"):
        root_base = base[base["root"] == root].set_index("state")
        unconditional = root_base.loc["unconditional"]
        for state in ["trapped", "broken"]:
            s = part[part["state"] == state]
            if s.empty or state not in root_base.index:
                continue
            state_row = root_base.loc[state]
            month_share = s.groupby("month").size().max() / len(s)
            week_share = s.groupby("week").size().max() / len(s)
            years_with_min_rows = int((s.groupby("year").size() >= int(gates["min_days_per_state_per_year"])).sum())
            rows.append({
                "root": root,
                "state": state,
                "days": int(len(s)),
                "years_with_min_rows": years_with_min_rows,
                "rest_range_ratio_lift_vs_unconditional": state_row["median_rest_rth_range_div_first_hour_range"] - unconditional["median_rest_rth_range_div_first_hour_range"],
                "new_rth_extreme_rate_lift_vs_unconditional": state_row["new_rth_high_or_low_after_10_30_rate"] - unconditional["new_rth_high_or_low_after_10_30_rate"],
                "chop_index_lift_vs_unconditional": state_row["mean_chop_index"] - unconditional["mean_chop_index"],
                "largest_month_share": month_share,
                "largest_week_share": week_share,
                "sparse": len(s) < int(gates[f"min_{state}_days"]),
                "concentrated": bool(month_share > float(gates["max_largest_month_share"]) or week_share > float(gates["max_largest_week_share"])),
            })
    return pd.DataFrame(rows)


def phase1_verdict(session: pd.DataFrame, cfg: dict[str, Any]) -> tuple[str, list[str]]:
    if session.empty:
        return "incomplete_reproducibility", ["no_joined_sessions"]

    gates = cfg["phase1_gates"]
    reasons: list[str] = []
    stability = concentration_or_stability(session, cfg)

    for root, part in session.groupby("root"):
        counts = part["state"].value_counts().to_dict()
        for state in ["trapped", "broken"]:
            n = int(counts.get(state, 0))
            if n < int(gates[f"min_{state}_days"]):
                reasons.append(f"{root}:{state}_too_sparse:{n}")

        root_stability = stability[stability["root"] == root]
        for state in ["trapped", "broken"]:
            s = root_stability[root_stability["state"] == state]
            if s.empty:
                reasons.append(f"{root}:{state}_missing_stability_row")
                continue
            years = int(s["years_with_min_rows"].iloc[0])
            if years < int(gates[f"min_years_with_{state}"]):
                reasons.append(f"{root}:{state}_insufficient_year_splits:{years}")
            if bool(s["concentrated"].iloc[0]):
                reasons.append(f"{root}:{state}_concentrated")

    material = False
    for _, row in stability.iterrows():
        material = material or abs(float(row["rest_range_ratio_lift_vs_unconditional"])) >= float(gates["min_rest_range_ratio_lift"])
        material = material or abs(float(row["new_rth_extreme_rate_lift_vs_unconditional"])) >= float(gates["min_new_rth_extreme_lift"])
        material = material or abs(float(row["chop_index_lift_vs_unconditional"])) >= float(gates["min_chop_index_lift"])
    if not material:
        reasons.append("no_material_state_separation")

    if reasons:
        return "session_regime_proxy_rejected", reasons
    return "session_regime_proxy_diagnostic_only", []


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, lineterminator="\n")


def write_source_lineage(path: Path, cfg: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    windows = cfg["session_windows"]
    lines = [
        "# Source Lineage",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Source | Path | File size bytes | Rows | First | Last | Role |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for s in sources:
        lines.append(
            f"| {s['label']} | `{s['path']}` | {s['size']} | {s['rows']} | {s['first']} | {s['last']} | {s['role']} |"
        )
    lines.extend([
        "",
        "## Session Convention",
        "",
        f"Timezone: `{cfg['session_timezone']}`.",
        f"Globex boundary window: `{windows['globex_start_prior_day']}` prior local date through `{windows['rth_open']}` current local date.",
        f"First RTH hour state window: `{windows['rth_open']}` through `{windows['first_hour_end']}`.",
        f"Rest-of-RTH target window: `{windows['first_hour_end']}` through `{windows['rth_close']}`.",
        "",
        "## State Definition",
        "",
        "`trapped`: first-hour high is strictly below Globex high and first-hour low is strictly above Globex low.",
        "`broken`: first-hour high reaches/exceeds Globex high or first-hour low reaches/breaks Globex low.",
        "`broken_up`, `broken_down`, `broken_both`, and `near_boundary_but_not_broken` are diagnostic sub-states only.",
        "",
        "## Metric Definitions",
        "",
        "`rest_RTH_range`: high minus low from 10:30 through 16:00.",
        "`rest_RTH_range / first_hour_range`: rest-of-RTH range divided by completed first-hour range.",
        "`rest_RTH_trendiness`: abs(rest close - rest open) / max(rest range, tick size).",
        "`rotation_count`: count close-to-close sign changes inside rest-of-RTH after ignoring zero moves.",
        "`chop_index`: rotation_count / max(nonzero close move count - 1, 1).",
        "`VWAP_cross_count`: count of rest-of-RTH 1-minute bars spanning the completed first-hour HLC3 volume-weighted VWAP.",
        "`new_RTH_high_after_10_30`: rest high exceeds first-hour high.",
        "`new_RTH_low_after_10_30`: rest low breaks first-hour low.",
        "`new_session_high_or_low_after_10_30`: rest breaks max(Globex high, first-hour high) or min(Globex low, first-hour low).",
        "",
        "## Lookahead Guard",
        "",
        "State classification uses only the completed Globex boundary window and completed 09:30-10:30 first-hour window. Rest-of-RTH outcomes are measured only after 10:30.",
        "",
        "## Data Windows",
        "",
        f"Primary Databento window: `{cfg['primary_date_filter']['start']}` through `{cfg['primary_date_filter']['end']}`.",
        f"Supplemental Databento window: `{cfg['supplemental_date_filter']['start']}` through `{cfg['supplemental_date_filter']['end']}` when requested.",
        "Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def source_info(path: Path, df: pd.DataFrame, label: str, role: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": repo_rel(path),
        "size": path.stat().st_size if path.exists() else 0,
        "rows": int(len(df)),
        "first": df["timestamp"].min().isoformat() if not df.empty else "",
        "last": df["timestamp"].max().isoformat() if not df.empty else "",
        "role": role,
    }


def write_verdict(
    path: Path,
    cfg: dict[str, Any],
    verdict: str,
    gate_reasons: list[str],
    summary: pd.DataFrame,
    report_dir: Path,
) -> None:
    lines = [
        "# Inside Day Trap Verdict",
        "",
        f"Issue: {cfg['issue_url']}",
        f"Parent roadmap: {cfg['parent_issue_url']}",
        "",
        f"Verdict: `{verdict}`",
        "",
        "This is a Phase 1 state-variable audit only. It does not run RSI, continuation, VWAP-reversion, or any other strategy signal and cannot approve trading.",
        "",
        "## Interpretation",
        "",
    ]
    if verdict == "session_regime_proxy_rejected":
        lines.append("- First-hour containment versus Globex did not pass the frozen Phase 1 gates as a robust standalone state variable.")
    elif verdict == "session_regime_proxy_diagnostic_only":
        lines.append("- First-hour containment versus Globex shows diagnostic separation, but remains non-tradable by itself.")
        lines.append("- Any continuation or VWAP-reversion signal test must be opened as a separate frozen diagnostic issue.")
    elif verdict == "session_regime_proxy_useful_no_signal_edge":
        lines.append("- The state variable is useful enough for a later frozen signal diagnostic, but no signal edge was tested here.")
    else:
        lines.append("- Reproducibility is incomplete; do not interpret this as market evidence.")
    lines.extend(["", "Gate reasons:"])
    lines.extend([f"- {reason}" for reason in gate_reasons] or ["- none"])
    lines.extend([
        "",
        "Guardrails:",
        "- No RSI or other strategy signal was run.",
        "- No paper/live approval.",
        "- No NinjaTrader execution.",
        "- No broker/IBKR work.",
        "- No primary validation candidate.",
        "",
        "## Primary Summary",
        "",
        "| Root | State | Days | Median rest / first-hour range | New RTH extreme rate | New session extreme rate | Mean chop index | Mean first-hour VWAP cross count |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for _, row in summary.sort_values(["root", "state"]).iterrows():
        lines.append(
            "| {root} | {state} | {days:.0f} | {ratio:.3f} | {ext:.3f} | {sess:.3f} | {chop:.3f} | {vwap:.2f} |".format(
                root=row["root"],
                state=row["state"],
                days=row["days"],
                ratio=row["median_rest_rth_range_div_first_hour_range"],
                ext=row["new_rth_high_or_low_after_10_30_rate"],
                sess=row["new_session_high_or_low_after_10_30_rate"],
                chop=row["mean_chop_index"],
                vwap=row["mean_first_hour_vwap_cross_count"],
            )
        )
    lines.extend([
        "",
        "## Artifacts",
        "",
        f"- Report directory: `{repo_rel(report_dir)}`",
        "- Required tables: `inside_trap_state_summary.csv`, `rest_of_rth_outcomes_by_state.csv`, `new_high_low_metrics.csv`, `chop_rotation_metrics.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.",
        f"- Final verdict: `{verdict}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_outputs(df: pd.DataFrame, cfg: dict[str, Any], out_dir: Path, label: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], str, list[str]]:
    session = build_session_table(df, cfg)
    if not session.empty:
        session = add_rest_vwap_cross_counts(session, df, cfg)
    verdict, reasons = phase1_verdict(session, cfg)
    tables = {
        "session_state_table": session,
        "inside_trap_state_summary": summarize_state(session) if not session.empty else pd.DataFrame(),
        "rest_of_rth_outcomes_by_state": summarize_outcomes(session) if not session.empty else pd.DataFrame(),
        "rest_of_rth_outcomes_by_sub_state": summarize_outcomes(session, "sub_state") if not session.empty else pd.DataFrame(),
        "new_high_low_metrics": new_high_low_metrics(session) if not session.empty else pd.DataFrame(),
        "chop_rotation_metrics": chop_rotation_metrics(session) if not session.empty else pd.DataFrame(),
        "year_splits": year_splits(session) if not session.empty else pd.DataFrame(),
        "concentration_or_stability_checks": concentration_or_stability(session, cfg) if not session.empty else pd.DataFrame(),
    }
    return session, tables, verdict, reasons


def main() -> int:
    args = parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    out_dir = args.out_dir or Path("reports") / f"inside_day_trap_{args.date}"
    top_report = Path(f"INSIDE_DAY_TRAP_{args.date}.md")
    if out_dir.exists():
        if not args.force:
            raise SystemExit(f"Output exists: {out_dir}; pass --force")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data_path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
    full = read_ohlcv(data_path, cfg, "databento_ohlcv_1m")
    primary = filter_by_local_session_date(full, cfg, cfg["primary_date_filter"])
    session, tables, verdict, reasons = build_outputs(primary, cfg, out_dir, "primary")

    write_csv(tables["session_state_table"], out_dir / "session_state_table.csv")
    write_csv(tables["inside_trap_state_summary"], out_dir / "inside_trap_state_summary.csv")
    write_csv(tables["rest_of_rth_outcomes_by_state"], out_dir / "rest_of_rth_outcomes_by_state.csv")
    write_csv(tables["rest_of_rth_outcomes_by_sub_state"], out_dir / "rest_of_rth_outcomes_by_sub_state.csv")
    write_csv(tables["new_high_low_metrics"], out_dir / "new_high_low_metrics.csv")
    write_csv(tables["chop_rotation_metrics"], out_dir / "chop_rotation_metrics.csv")
    write_csv(tables["year_splits"], out_dir / "year_splits.csv")
    write_csv(tables["concentration_or_stability_checks"], out_dir / "concentration_or_stability_checks.csv")

    supplemental_table = pd.DataFrame()
    if args.include_supplemental:
        supplemental = filter_by_local_session_date(full, cfg, cfg["supplemental_date_filter"])
        _, supplemental_tables, _, _ = build_outputs(supplemental, cfg, out_dir, "supplemental")
        supplemental_table = supplemental_tables["rest_of_rth_outcomes_by_state"]
        supplemental_table.insert(0, "window", cfg["supplemental_date_filter"]["label"])
    write_csv(supplemental_table, out_dir / "supplemental_2026_q1.csv")

    local_table = pd.DataFrame()
    sources = [source_info(data_path, full, "databento_ohlcv_1m_full_view", "primary_and_supplemental_source")]
    if args.local_parity:
        local_path = Path(cfg["data_sources"]["local_ninja_ohlcv_1m"])
        if local_path.exists():
            local_full = read_ohlcv(local_path, cfg, "local_ninja_ohlcv_1m")
            sources.append(source_info(local_path, local_full, "local_ninja_ohlcv_1m", "under_sampled_recency_sanity_only"))
            _, local_tables, _, _ = build_outputs(local_full, cfg, out_dir, "local")
            local_table = local_tables["rest_of_rth_outcomes_by_state"]
            if not local_table.empty:
                local_table.insert(0, "window", "local_ninja_under_sampled_sanity_only")
    write_csv(local_table, out_dir / "local_ninja_parity_check.csv")

    write_source_lineage(out_dir / "source_lineage.md", cfg, sources)
    summary = tables["rest_of_rth_outcomes_by_state"]
    write_verdict(out_dir / "VERDICT.md", cfg, verdict, reasons, summary, out_dir)
    write_verdict(top_report, cfg, verdict, reasons, summary, out_dir)

    metadata = {
        "schema_version": 1,
        "issue": cfg["issue_url"],
        "parent_issue": cfg["parent_issue_url"],
        "phase": "state_variable_audit_only",
        "verdict": verdict,
        "gate_reasons": reasons,
        "primary_date_filter": cfg["primary_date_filter"],
        "supplemental_included": bool(args.include_supplemental),
        "local_parity_included": bool(args.local_parity),
        "strategy_signals_ran": False,
        "rsi_ran": False,
        "permitted_verdicts": cfg["permitted_verdicts"],
        "forbidden_verdicts": cfg["forbidden_verdicts"],
        "outputs": sorted([
            top_report.name,
            "VERDICT.md",
            "chop_rotation_metrics.csv",
            "concentration_or_stability_checks.csv",
            "inside_trap_state_summary.csv",
            "local_ninja_parity_check.csv",
            "new_high_low_metrics.csv",
            "rest_of_rth_outcomes_by_state.csv",
            "rest_of_rth_outcomes_by_sub_state.csv",
            "session_state_table.csv",
            "source_lineage.md",
            "supplemental_2026_q1.csv",
            "triage_metadata.json",
            "year_splits.csv",
        ]),
    }
    (out_dir / "triage_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir}; verdict={verdict}; top_report={top_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
