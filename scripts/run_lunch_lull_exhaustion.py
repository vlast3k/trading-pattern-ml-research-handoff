#!/usr/bin/env python3
"""Issue #27 Lunch Lull Exhaustion state audit.

This Phase 1 audit tests whether an unusually large RTH morning range
predicts lunch-window contraction, VWAP reversion, or failed continuation.
It does not run strategy signals and cannot approve trading.
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/lunch_lull_exhaustion_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--include-supplemental", action="store_true")
    p.add_argument("--local-parity", action="store_true")
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
    mapped = {name: pick(cols, names) for name, names in cfg["column_aliases"].items()}
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


def parse_hhmm(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def add_local_time(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    local = out["timestamp"].dt.tz_convert(cfg["session_timezone"])
    out["local_timestamp"] = local
    out["session_date"] = local.dt.date.astype(str)
    out["local_minute"] = local.dt.hour * 60 + local.dt.minute
    out["hlc3"] = (out["high"] + out["low"] + out["close"]) / 3.0
    out["pv"] = out["hlc3"] * out["volume"]
    return out


def window_rows(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    s = parse_hhmm(start)
    e = parse_hhmm(end)
    return df[(df["local_minute"] >= s) & (df["local_minute"] < e)].copy()


def agg_window(x: pd.DataFrame, prefix: str) -> pd.DataFrame:
    grouped = x.groupby(["root", "session_date"], as_index=False).agg(
        **{
            f"{prefix}_first_timestamp": ("timestamp", "min"),
            f"{prefix}_last_timestamp": ("timestamp", "max"),
            f"{prefix}_open": ("open", "first"),
            f"{prefix}_high": ("high", "max"),
            f"{prefix}_low": ("low", "min"),
            f"{prefix}_close": ("close", "last"),
            f"{prefix}_volume": ("volume", "sum"),
            f"{prefix}_pv": ("pv", "sum"),
            f"{prefix}_bar_count": ("timestamp", "size"),
        }
    )
    grouped[f"{prefix}_vwap"] = grouped[f"{prefix}_pv"] / grouped[f"{prefix}_volume"].replace(0, pd.NA)
    return grouped


def build_session_table(df: pd.DataFrame, cfg: dict[str, Any], window: dict[str, Any], cohort: str) -> pd.DataFrame:
    x = add_local_time(df, cfg)
    x = x[(x["session_date"] >= str(window["start"])) & (x["session_date"] <= str(window["end"]))].copy()
    windows = cfg["session_windows"]
    morning = agg_window(window_rows(x, windows["rth_morning_start"], windows["rth_morning_end"]), "morning")
    lunch = agg_window(window_rows(x, windows["lunch_start"], windows["lunch_end"]), "lunch")
    out = morning.merge(lunch, on=["root", "session_date"], how="inner")
    out = out.sort_values(["root", "session_date"]).reset_index(drop=True)
    out["cohort"] = cohort

    tick = float(cfg["tick_size"])
    sd = cfg["state_definition"]
    od = cfg["outcome_definition"]
    out["morning_range"] = out["morning_high"] - out["morning_low"]
    out["morning_reference_median_20"] = out.groupby("root")["morning_range"].transform(
        lambda s: s.shift(1).rolling(int(sd["rolling_reference_sessions"]), min_periods=int(sd["rolling_reference_sessions"])).median()
    )
    out["morning_range_ratio"] = out["morning_range"] / out["morning_reference_median_20"]
    out["morning_state"] = "unclassified"
    out.loc[out["morning_range_ratio"] <= float(sd["exhaustion_threshold"]), "morning_state"] = "standard"
    out.loc[out["morning_range_ratio"] > float(sd["exhaustion_threshold"]), "morning_state"] = "exhaustion"
    out["morning_range_ratio_bin"] = pd.cut(
        out["morning_range_ratio"],
        [-math.inf, 0.7, 1.0, 1.3, 1.5, 2.0, math.inf],
        labels=["le_0_7", "0_7_to_1_0", "1_0_to_1_3", "1_3_to_1_5", "1_5_to_2_0", "gt_2_0"],
    )

    out["lunch_range"] = out["lunch_high"] - out["lunch_low"]
    out["lunch_range_div_morning_range"] = out["lunch_range"] / out["morning_range"]
    out["lunch_range_contraction"] = out["lunch_range"] < out["morning_range"] * float(od["lunch_contraction_fixed_ratio"])
    denom = out["lunch_range"].clip(lower=tick)
    out["lunch_trendiness"] = (out["lunch_close"] - out["lunch_open"]).abs() / denom
    out["lunch_signed_trendiness"] = (out["lunch_close"] - out["lunch_open"]) / denom
    out["morning_signed_direction"] = (out["morning_close"] - out["morning_open"]).apply(lambda v: 1 if v > 0 else (-1 if v < 0 else 0))
    out["lunch_signed_direction"] = (out["lunch_close"] - out["lunch_open"]).apply(lambda v: 1 if v > 0 else (-1 if v < 0 else 0))
    out["trend_continuation_failure"] = (out["morning_signed_direction"] != 0) & (out["lunch_signed_direction"] == -out["morning_signed_direction"])
    out["new_high_or_low_during_lunch"] = (out["lunch_high"] > out["morning_high"]) | (out["lunch_low"] < out["morning_low"])
    out["close_location_within_lunch_range"] = (out["lunch_close"] - out["lunch_low"]) / out["lunch_range"].clip(lower=tick)
    out["vwap_cross"] = (out["lunch_low"] <= out["morning_vwap"]) & (out["lunch_high"] >= out["morning_vwap"])
    extension_points = (out["morning_close"] - out["morning_vwap"]).abs()
    out["vwap_touch_after_morning_extension"] = (extension_points > float(od["morning_extension_min_points"])) & out["vwap_cross"]
    out["year"] = pd.to_datetime(out["session_date"]).dt.year
    out["month"] = pd.to_datetime(out["session_date"]).dt.strftime("%Y-%m")
    out["week"] = pd.to_datetime(out["session_date"]).dt.strftime("%G-W%V")
    return out


def summarize(part: pd.DataFrame, state_label: str) -> dict[str, Any]:
    if part.empty:
        return {
            "state": state_label,
            "days": 0,
            "mean_lunch_range": 0.0,
            "median_lunch_range": 0.0,
            "mean_lunch_range_div_morning_range": 0.0,
            "median_lunch_range_div_morning_range": 0.0,
            "lunch_range_contraction_rate": 0.0,
            "mean_lunch_trendiness": 0.0,
            "median_lunch_trendiness": 0.0,
            "mean_lunch_signed_trendiness": 0.0,
            "median_lunch_signed_trendiness": 0.0,
            "vwap_cross_rate": 0.0,
            "vwap_touch_after_morning_extension_rate": 0.0,
            "trend_continuation_failure_rate": 0.0,
            "new_high_or_low_during_lunch_rate": 0.0,
            "mean_close_location_within_lunch_range": 0.0,
            "median_close_location_within_lunch_range": 0.0,
        }
    return {
        "state": state_label,
        "days": int(len(part)),
        "mean_lunch_range": float(part["lunch_range"].mean()),
        "median_lunch_range": float(part["lunch_range"].median()),
        "mean_lunch_range_div_morning_range": float(part["lunch_range_div_morning_range"].mean()),
        "median_lunch_range_div_morning_range": float(part["lunch_range_div_morning_range"].median()),
        "lunch_range_contraction_rate": float(part["lunch_range_contraction"].mean()),
        "mean_lunch_trendiness": float(part["lunch_trendiness"].mean()),
        "median_lunch_trendiness": float(part["lunch_trendiness"].median()),
        "mean_lunch_signed_trendiness": float(part["lunch_signed_trendiness"].mean()),
        "median_lunch_signed_trendiness": float(part["lunch_signed_trendiness"].median()),
        "vwap_cross_rate": float(part["vwap_cross"].mean()),
        "vwap_touch_after_morning_extension_rate": float(part["vwap_touch_after_morning_extension"].mean()),
        "trend_continuation_failure_rate": float(part["trend_continuation_failure"].mean()),
        "new_high_or_low_during_lunch_rate": float(part["new_high_or_low_during_lunch"].mean()),
        "mean_close_location_within_lunch_range": float(part["close_location_within_lunch_range"].mean()),
        "median_close_location_within_lunch_range": float(part["close_location_within_lunch_range"].median()),
    }


def state_summary(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["morning_state"] != "unclassified"].copy()
    for root, root_part in x.groupby("root"):
        total = len(root_part)
        for state in ["standard", "exhaustion"]:
            part = root_part[root_part["morning_state"] == state]
            rows.append({
                "root": root,
                "morning_state": state,
                "days": int(len(part)),
                "share": float(len(part) / total) if total else 0.0,
                "mean_morning_range": float(part["morning_range"].mean()) if len(part) else 0.0,
                "median_morning_range": float(part["morning_range"].median()) if len(part) else 0.0,
                "mean_morning_range_ratio": float(part["morning_range_ratio"].mean()) if len(part) else 0.0,
                "median_morning_range_ratio": float(part["morning_range_ratio"].median()) if len(part) else 0.0,
            })
    return pd.DataFrame(rows)


def outcomes_by_state(table: pd.DataFrame, cohort: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["morning_state"] != "unclassified"].copy()
    for root, root_part in x.groupby("root"):
        rows.append({"root": root, "cohort": cohort, **summarize(root_part, "unconditional")})
        for state in ["standard", "exhaustion"]:
            rows.append({"root": root, "cohort": cohort, **summarize(root_part[root_part["morning_state"] == state], state)})
    return pd.DataFrame(rows)


def bin_diagnostics(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["morning_range_ratio_bin"].notna()].copy()
    for (root, bin_name), part in x.groupby(["root", "morning_range_ratio_bin"], observed=False):
        rows.append({"root": root, "morning_range_ratio_bin": str(bin_name), **summarize(part, str(bin_name))})
    return pd.DataFrame(rows)


def year_splits(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["morning_state"] != "unclassified"].copy()
    for (root, year), root_year in x.groupby(["root", "year"]):
        rows.append({"root": root, "year": int(year), **summarize(root_year, "unconditional")})
        for state in ["standard", "exhaustion"]:
            rows.append({"root": root, "year": int(year), **summarize(root_year[root_year["morning_state"] == state], state)})
    return pd.DataFrame(rows)


def metric_subset(table: pd.DataFrame, cohort: str, cols: list[str]) -> pd.DataFrame:
    return outcomes_by_state(table, cohort).reindex(columns=cols)


def stability_checks(table: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, bool, list[str]]:
    x = table[table["morning_state"] != "unclassified"].copy()
    base = outcomes_by_state(x, x["cohort"].iloc[0] if len(x) else "primary")
    rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    gates = cfg["phase1_gates"]

    for root, root_part in x.groupby("root"):
        base_row = base[(base["root"] == root) & (base["state"] == "unconditional")].iloc[0]
        ex = root_part[root_part["morning_state"] == "exhaustion"]
        ex_row = base[(base["root"] == root) & (base["state"] == "exhaustion")].iloc[0]
        years_ok = int(
            ex.groupby("year").size().reset_index(name="days").query("days >= @gates['min_days_per_state_per_year']")["year"].nunique()
        )
        range_lift = float(ex_row["median_lunch_range_div_morning_range"]) - float(base_row["median_lunch_range_div_morning_range"])
        contraction_lift = float(ex_row["lunch_range_contraction_rate"]) - float(base_row["lunch_range_contraction_rate"])
        failure_lift = float(ex_row["trend_continuation_failure_rate"]) - float(base_row["trend_continuation_failure_rate"])
        month_counts = ex.groupby("month").size().sort_values(ascending=False)
        week_counts = ex.groupby("week").size().sort_values(ascending=False)
        largest_month_share = float(month_counts.iloc[0] / len(ex)) if len(ex) and len(month_counts) else 0.0
        largest_week_share = float(week_counts.iloc[0] / len(ex)) if len(ex) and len(week_counts) else 0.0
        sparse = len(ex) < int(gates["min_exhaustion_days"])
        unstable = years_ok < int(gates["min_years_with_exhaustion"])
        materially_separates = (
            abs(range_lift) >= float(gates["min_lunch_range_ratio_lift"])
            or abs(contraction_lift) >= float(gates["min_contraction_rate_lift"])
            or abs(failure_lift) >= float(gates["min_failure_rate_lift"])
        )
        if sparse:
            reasons.append(f"{root}:exhaustion_too_sparse:{len(ex)}")
        if unstable:
            reasons.append(f"{root}:exhaustion_not_stable_across_years:{years_ok}")
        if not materially_separates:
            reasons.append(f"{root}:exhaustion_does_not_materially_separate_lunch_behavior")
        rows.append({
            "root": root,
            "state": "exhaustion",
            "days": int(len(ex)),
            "years_with_min_rows": years_ok,
            "median_lunch_range_div_morning_range_lift_vs_unconditional": range_lift,
            "contraction_rate_lift_vs_unconditional": contraction_lift,
            "trend_continuation_failure_rate_lift_vs_unconditional": failure_lift,
            "largest_month_share": largest_month_share,
            "largest_week_share": largest_week_share,
            "sparse": bool(sparse),
            "unstable_year_splits": bool(unstable),
            "materially_separates": bool(materially_separates),
        })
    return pd.DataFrame(rows), not reasons, reasons


def supplemental_or_parity(table: pd.DataFrame, cohort: str) -> pd.DataFrame:
    out = outcomes_by_state(table, cohort)
    out.insert(0, "status", "under_sampled_sanity_only" if "ninja" in cohort else "supplemental_not_pooled")
    return out


def source_info(df: pd.DataFrame, label: str, path: Path, role: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": repo_rel(path),
        "size_bytes": path.stat().st_size if path.exists() else 0,
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


def write_source_lineage(out: Path, cfg: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    w = cfg["session_windows"]
    od = cfg["outcome_definition"]
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
        "## Session Convention",
        "",
        f"Timezone: `{cfg['session_timezone']}`.",
        f"RTH morning state window: `{w['rth_morning_start']}` through `{w['rth_morning_end']}`.",
        f"Lunch target window: `{w['lunch_start']}` through `{w['lunch_end']}`.",
        "",
        "## Metric Definitions",
        "",
        f"`Lunch_range_contraction`: lunch range < morning range * `{od['lunch_contraction_fixed_ratio']}`.",
        "`Lunch_trendiness`: abs(lunch close - lunch open) / max(lunch high - lunch low, tick size).",
        "`VWAP`: HLC3 volume-weighted average price over the completed morning window.",
        "`VWAP_cross`: lunch high/low spans the completed morning VWAP.",
        "`VWAP_touch_after_morning_extension`: morning close differs from morning VWAP and lunch spans that morning VWAP.",
        "`Trend_continuation_failure`: lunch signed direction is opposite the morning signed direction.",
        "`New_high_or_low_during_lunch`: lunch high exceeds morning high or lunch low breaks morning low.",
        "`Close_location_within_lunch_range`: (lunch close - lunch low) / max(lunch range, tick size).",
        "",
        "## Data Windows",
        "",
        f"Primary Databento window: `{cfg['primary_date_filter']['start']}` through `{cfg['primary_date_filter']['end']}`.",
        f"Supplemental Databento window: `{cfg['supplemental_date_filter']['start']}` through `{cfg['supplemental_date_filter']['end']}` when requested.",
        "Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.",
        "",
        "## Lookahead Guard",
        "",
        "Morning state uses only the completed 09:30-11:30 morning window and prior completed morning sessions. Lunch outcomes are measured after 11:30 and are not used for state classification.",
    ]
    (out / "source_lineage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verdict(out: Path, cfg: dict[str, Any], verdict: str, reasons: list[str]) -> None:
    lines = [
        "# Lunch Lull Exhaustion Verdict",
        "",
        f"Issue: {cfg['issue_url']}",
        f"Parent roadmap: {cfg['parent_issue_url']}",
        "",
        f"Verdict: `{verdict}`",
        "",
        "This is a Phase 1 state-variable audit only. It does not run RSI or any other strategy signal and cannot approve trading.",
        "",
        "## Interpretation",
        "",
    ]
    if verdict == "session_regime_proxy_rejected":
        lines += [
            "- Morning exhaustion did not pass the Phase 1 state-variable gate.",
            "- Do not open a lunch signal diagnostic from this result without separate review.",
        ]
    else:
        lines += [
            "- Morning exhaustion shows enough diagnostic separation to continue research, but remains non-tradable by itself.",
            "- Any lunch VWAP or range-contraction signal test must be opened as a separate issue.",
        ]
    lines += [
        "",
        "Gate reasons:",
    ]
    lines += [f"- {reason}" for reason in reasons] or ["- none"]
    lines += [
        "",
        "Guardrails:",
        "- No RSI or other strategy signal was run.",
        "- No paper/live approval.",
        "- No NinjaTrader execution.",
        "- No broker/IBKR work.",
        "- No primary validation candidate.",
    ]
    (out / "VERDICT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_top_report(date: str, out: Path, verdict: str) -> Path:
    target = Path(f"LUNCH_LULL_EXHAUSTION_{date}.md")
    text = [(out / "VERDICT.md").read_text(encoding="utf-8").rstrip(), ""]
    summary_path = out / "lunch_outcomes_by_morning_state.csv"
    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        text += [
            "## Primary Summary",
            "",
            "| Root | State | Days | Median lunch range / morning range | Contraction rate | VWAP cross rate | Continuation failure rate |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for row in summary.to_dict("records"):
            text.append(
                f"| {row['root']} | {row['state']} | {row['days']} | {float(row['median_lunch_range_div_morning_range']):.3f} | {float(row['lunch_range_contraction_rate']):.3f} | {float(row['vwap_cross_rate']):.3f} | {float(row['trend_continuation_failure_rate']):.3f} |"
            )
        text += [
            "",
            "## Artifacts",
            "",
            f"- Report directory: `{repo_rel(out)}`",
            "- Required tables: `morning_state_summary.csv`, `lunch_outcomes_by_morning_state.csv`, `vwap_reversion_metrics.csv`, `trend_continuation_failure_metrics.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.",
            f"- Final verdict: `{verdict}`.",
            "",
        ]
    target.write_text("\n".join(text), encoding="utf-8")
    return target


def main() -> None:
    args = parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    out = args.out_dir or Path(f"reports/lunch_lull_exhaustion_{args.date}")
    prepare_output_dir(out, args.force)

    primary_path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
    full = read_ohlcv(primary_path, cfg, "databento_ohlcv_1m")
    sources = [source_info(full, "databento_ohlcv_1m_full_view", primary_path, "primary_and_supplemental_source")]
    primary = build_session_table(full, cfg, cfg["primary_date_filter"], "primary_2023_2025")
    primary.to_csv(out / "session_state_table.csv", index=False)
    state_summary(primary).to_csv(out / "morning_state_summary.csv", index=False)
    outcomes_by_state(primary, "primary_2023_2025").to_csv(out / "lunch_outcomes_by_morning_state.csv", index=False)
    metric_cols = ["root", "cohort", "state", "days", "vwap_cross_rate", "vwap_touch_after_morning_extension_rate"]
    metric_subset(primary, "primary_2023_2025", metric_cols).to_csv(out / "vwap_reversion_metrics.csv", index=False)
    failure_cols = ["root", "cohort", "state", "days", "trend_continuation_failure_rate", "new_high_or_low_during_lunch_rate", "mean_close_location_within_lunch_range", "median_close_location_within_lunch_range"]
    metric_subset(primary, "primary_2023_2025", failure_cols).to_csv(out / "trend_continuation_failure_metrics.csv", index=False)
    year_splits(primary).to_csv(out / "year_splits.csv", index=False)
    bin_diagnostics(primary).to_csv(out / "diagnostic_bin_grid.csv", index=False)
    stability, gate_ok, reasons = stability_checks(primary, cfg)
    stability.to_csv(out / "stability_checks.csv", index=False)

    if args.include_supplemental:
        supplemental = build_session_table(full, cfg, cfg["supplemental_date_filter"], "supplemental_2026_q1")
        supplemental_or_parity(supplemental, "supplemental_2026_q1").to_csv(out / "supplemental_2026_q1.csv", index=False)
    else:
        pd.DataFrame([{"status": "not_requested"}]).to_csv(out / "supplemental_2026_q1.csv", index=False)

    if args.local_parity:
        local_path = Path(cfg["data_sources"].get("local_ninja_ohlcv_1m", ""))
        if local_path.exists():
            local = read_ohlcv(local_path, cfg, "local_ninja_ohlcv_1m")
            sources.append(source_info(local, "local_ninja_ohlcv_1m", local_path, "under_sampled_recency_sanity_only"))
            local_with_dates = add_local_time(local, cfg)
            local_window = {
                "start": str(local_with_dates["session_date"].min()),
                "end": str(local_with_dates["session_date"].max()),
                "label": "local_ninja_available",
            }
            local_table = build_session_table(local, cfg, local_window, "local_ninja_parity")
            supplemental_or_parity(local_table, "local_ninja_parity").to_csv(out / "local_ninja_parity_check.csv", index=False)
        else:
            pd.DataFrame([{"status": "not_available", "path": local_path.as_posix()}]).to_csv(out / "local_ninja_parity_check.csv", index=False)
    else:
        pd.DataFrame([{"status": "not_requested"}]).to_csv(out / "local_ninja_parity_check.csv", index=False)

    verdict = "session_regime_proxy_diagnostic_only" if gate_ok else "session_regime_proxy_rejected"
    write_source_lineage(out, cfg, sources)
    write_verdict(out, cfg, verdict, reasons)
    top_report = write_top_report(args.date, out, verdict)
    metadata = {
        "schema_version": 1,
        "issue": cfg["issue_url"],
        "parent_issue": cfg["parent_issue_url"],
        "verdict": verdict,
        "phase": "state_variable_audit_only",
        "strategy_signals_ran": False,
        "rsi_ran": False,
        "primary_date_filter": cfg["primary_date_filter"],
        "supplemental_included": bool(args.include_supplemental),
        "local_parity_included": bool(args.local_parity),
        "gate_ok": gate_ok,
        "gate_reasons": reasons,
        "top_level_report": repo_rel(top_report),
        "outputs": sorted([p.name for p in out.iterdir()] + [top_report.name, "triage_metadata.json"]),
        "permitted_verdicts": cfg["permitted_verdicts"],
        "forbidden_verdicts": cfg["forbidden_verdicts"],
    }
    (out / "triage_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}; verdict={verdict}; top_report={top_report}")


if __name__ == "__main__":
    main()
