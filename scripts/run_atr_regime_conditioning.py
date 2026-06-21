#!/usr/bin/env python3
"""Issue #19 ATR-regime conditioning audit.

Runs the Phase 1 state audit for TR_{t-1}/ATR20. Phase 2 is not
implemented in this scaffold because strategy interpretation should only follow
a local review of the state proxy outputs. This script cannot approve
paper/live trading or directly promote a primary validation candidate.
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


PHASE2_SKIP_REASON = "phase2_not_implemented_in_initial_scaffold"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/atr_regime_conditioning_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--run-phase2",
        action="store_true",
        help="Accepted only to record intent; Phase 2 signal execution is intentionally not implemented in this scaffold.",
    )
    p.add_argument("--local-parity", action="store_true", help="Run Phase 1 summary on local Ninja OHLCV if present.")
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


def empty_signal_outputs(out: Path, reason: str) -> None:
    perf_cols = ["signal", "state", "slippage_ticks_per_side", "trades", "net_dollars", "profit_factor", "skip_reason"]
    pd.DataFrame(columns=perf_cols).assign(skip_reason=reason).to_csv(out / "signal_performance_by_state.csv", index=False)
    pd.DataFrame(columns=perf_cols).assign(skip_reason=reason).to_csv(out / "signal_controls_unconditional.csv", index=False)
    concentration_cols = ["signal", "state", "largest_winner_share", "best_day_share", "best_week_share", "net_excluding_largest", "skip_reason"]
    pd.DataFrame(columns=concentration_cols).assign(skip_reason=reason).to_csv(out / "concentration_by_state.csv", index=False)


def write_lineage(out: Path, cfg: dict[str, Any], sources: list[dict[str, Any]]) -> None:
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
        "## Lookahead guard",
        "",
        "State for day t uses prior-day TR and ATR over completed prior sessions only. Current-day high/low is not included in the state for that day.",
        "",
        "## Scope guard",
        "",
        "This scaffold writes Phase 2 placeholders only. It cannot approve paper/live trading and cannot directly promote a candidate.",
    ]
    (out / "source_lineage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verdict(out: Path, cfg: dict[str, Any], ok: bool, reasons: list[str], phase2_requested: bool) -> str:
    if not ok:
        verdict = "regime_proxy_rejected"
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
        "## Phase 2",
        "",
        f"Requested: {phase2_requested}",
        "Ran: false",
        f"Skip reason: `{PHASE2_SKIP_REASON}`",
        "",
        "Interpretation:",
        "- If Phase 1 passes, this scaffold still reports `incomplete_reproducibility` because signal definitions and Phase 2 controls have not been executed.",
        "- A worker must extend or run Phase 2 in a later commit before claiming signal-edge results.",
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
    target.write_text((out / "VERDICT.md").read_text(encoding="utf-8"), encoding="utf-8")
    return target


def main() -> None:
    args = parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    out = args.out_dir or Path(f"reports/atr_regime_conditioning_{args.date}")
    prepare_output_dir(out, args.force)

    primary_path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
    primary = read_ohlcv(primary_path, cfg, "databento_ohlcv_1m")
    sources = [source_info(primary, "databento_ohlcv_1m", primary_path, "primary_long_history")]

    daily = daily_state(primary, cfg)
    daily.to_csv(out / "daily_state_table.csv", index=False)
    distribution(daily).to_csv(out / "state_distribution_by_year.csv", index=False)
    behavior(daily, "state").to_csv(out / "next_day_behavior_by_state.csv", index=False)
    behavior(daily, "range_ratio_bin").to_csv(out / "bin_grid_diagnostics.csv", index=False)
    state_quality_summary(daily, cfg).to_csv(out / "state_quality_summary.csv", index=False)

    phase1_ok, reasons = phase1_gate(daily, cfg)
    empty_signal_outputs(out, PHASE2_SKIP_REASON if args.run_phase2 else "phase2_not_requested_in_initial_scaffold")

    if args.local_parity:
        local_path = Path(cfg["data_sources"].get("local_ninja_ohlcv_1m", ""))
        if local_path.exists():
            local = read_ohlcv(local_path, cfg, "local_ninja_ohlcv_1m")
            sources.append(source_info(local, "local_ninja_ohlcv_1m", local_path, "local_parity_recency_check"))
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
    }
    (out / "state_definition.json").write_text(json.dumps(state_def, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_lineage(out, cfg, sources)
    verdict = write_verdict(out, cfg, phase1_ok, reasons, args.run_phase2)
    top_report = write_top_level_report(args.date, out)
    metadata = {
        "schema_version": 1,
        "issue": cfg.get("issue_url"),
        "verdict": verdict,
        "phase1_ok": phase1_ok,
        "phase1_reasons": reasons,
        "phase2_requested": bool(args.run_phase2),
        "phase2_ran": False,
        "phase2_skip_reason": PHASE2_SKIP_REASON,
        "top_level_report": repo_rel(top_report),
        "outputs": sorted(path.name for path in out.iterdir()),
        "forbidden_verdicts": cfg.get("forbidden_verdicts", []),
    }
    (out / "triage_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}; verdict={verdict}; top_report={top_report}")


if __name__ == "__main__":
    main()
