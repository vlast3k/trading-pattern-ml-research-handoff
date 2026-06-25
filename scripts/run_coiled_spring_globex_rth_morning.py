#!/usr/bin/env python3
"""Issue #22 Coiled Spring Globex -> RTH morning state audit.

This is a Phase 1 state-variable audit only. It tests whether completed
Globex range state predicts the immediately following RTH morning behavior.
It must not run strategy signals or promote paper/live trading.
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
    p.add_argument("--config", type=Path, default=Path("config/coiled_spring_globex_rth_morning_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--local-parity", action="store_true")
    p.add_argument("--include-supplemental", action="store_true")
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


def parse_hhmm(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def add_local_time(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    local = out["timestamp"].dt.tz_convert(cfg.get("session_timezone", "America/New_York"))
    out["local_timestamp"] = local
    out["local_date"] = local.dt.date.astype(str)
    out["local_minute"] = local.dt.hour * 60 + local.dt.minute
    return out


def filter_session_window(df: pd.DataFrame, cfg: dict[str, Any], window: dict[str, Any]) -> pd.DataFrame:
    x = add_local_time(df, cfg)
    start = str(window["start"])
    end = str(window["end"])
    out = x[(x["session_date"] >= start) & (x["session_date"] <= end)].copy() if "session_date" in x else x
    if "session_date" not in x:
        local_dates = x["local_date"]
        out = x[(local_dates >= start) & (local_dates <= end)].copy()
    if out.empty:
        raise ValueError(f"No rows for window {window.get('label', '')}: {start}..{end}")
    out["data_window_label"] = window.get("label", f"{start}_to_{end}")
    return out.reset_index(drop=True)


def assign_session_dates(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_local_time(df, cfg)
    windows = cfg["session_windows"]
    globex_start = parse_hhmm(windows["globex_start"])
    globex_end = parse_hhmm(windows["globex_end"])
    rth_start = parse_hhmm(windows["rth_morning_start"])
    rth_end = parse_hhmm(windows["rth_morning_end"])

    local_date_dt = pd.to_datetime(x["local_date"])
    session_date_dt = local_date_dt.where(x["local_minute"] < globex_start, local_date_dt + pd.to_timedelta(1, unit="D"))
    x["session_date"] = session_date_dt.dt.date.astype(str)
    x["is_globex_context"] = (x["local_minute"] >= globex_start) | (x["local_minute"] < globex_end)
    x["is_rth_morning"] = (x["local_minute"] >= rth_start) & (x["local_minute"] < rth_end)
    return x


def agg_ohlcv(x: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return x.groupby(["root", "session_date"], as_index=False).agg(
        **{
            f"{prefix}_first_timestamp": ("timestamp", "min"),
            f"{prefix}_last_timestamp": ("timestamp", "max"),
            f"{prefix}_open": ("open", "first"),
            f"{prefix}_high": ("high", "max"),
            f"{prefix}_low": ("low", "min"),
            f"{prefix}_close": ("close", "last"),
            f"{prefix}_volume": ("volume", "sum"),
            f"{prefix}_bar_count": ("timestamp", "size"),
        }
    )


def daily_atr20(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_local_time(df, cfg)
    daily = x.groupby(["root", "local_date"], as_index=False).agg(high=("high", "max"), low=("low", "min"))
    daily = daily.sort_values(["root", "local_date"]).reset_index(drop=True)
    daily["daily_tr"] = daily["high"] - daily["low"]
    daily["rth_morning_atr20"] = daily.groupby("root")["daily_tr"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).mean())
    return daily.rename(columns={"local_date": "session_date"})[["root", "session_date", "rth_morning_atr20"]]


def build_session_table(df: pd.DataFrame, cfg: dict[str, Any], window: dict[str, Any], cohort: str) -> pd.DataFrame:
    assigned = assign_session_dates(df, cfg)
    assigned = assigned[(assigned["session_date"] >= str(window["start"])) & (assigned["session_date"] <= str(window["end"]))].copy()
    globex = agg_ohlcv(assigned[assigned["is_globex_context"]], "globex")
    rth = agg_ohlcv(assigned[assigned["is_rth_morning"]], "rth_morning")
    out = globex.merge(rth, on=["root", "session_date"], how="inner")
    out = out.merge(daily_atr20(df, cfg), on=["root", "session_date"], how="left")
    out = out.sort_values(["root", "session_date"]).reset_index(drop=True)
    out["cohort"] = cohort

    tick = float(cfg.get("tick_size", 0.25))
    sd = cfg["state_definition"]
    out["globex_range"] = out["globex_high"] - out["globex_low"]
    out["globex_reference_median_20"] = out.groupby("root")["globex_range"].transform(
        lambda s: s.shift(1).rolling(int(sd["rolling_reference_sessions"]), min_periods=int(sd["rolling_reference_sessions"])).median()
    )
    out["globex_range_ratio"] = out["globex_range"] / out["globex_reference_median_20"]
    out["globex_state"] = "unclassified"
    out.loc[out["globex_range_ratio"] < float(sd["compression_threshold"]), "globex_state"] = "compression"
    out.loc[
        (out["globex_range_ratio"] >= float(sd["compression_threshold"]))
        & (out["globex_range_ratio"] <= float(sd["expansion_threshold"])),
        "globex_state",
    ] = "neutral"
    out.loc[out["globex_range_ratio"] > float(sd["expansion_threshold"]), "globex_state"] = "expansion"
    out["globex_range_ratio_bin"] = pd.cut(
        out["globex_range_ratio"],
        [-math.inf, 0.5, 0.7, 0.9, 1.1, 1.3, math.inf],
        labels=["lt_0_5", "0_5_to_0_7", "0_7_to_0_9", "0_9_to_1_1", "1_1_to_1_3", "gt_1_3"],
    )

    out["rth_morning_range"] = out["rth_morning_high"] - out["rth_morning_low"]
    out["rth_morning_range_div_atr20"] = out["rth_morning_range"] / out["rth_morning_atr20"]
    denom = out["rth_morning_range"].clip(lower=tick)
    out["rth_morning_trendiness"] = (out["rth_morning_close"] - out["rth_morning_open"]).abs() / denom
    out["rth_morning_signed_trendiness"] = (out["rth_morning_close"] - out["rth_morning_open"]) / denom
    out["breached_globex_high"] = out["rth_morning_high"] > out["globex_high"]
    out["breached_globex_low"] = out["rth_morning_low"] < out["globex_low"]
    out["closed_outside_globex_range"] = (out["rth_morning_close"] > out["globex_high"]) | (out["rth_morning_close"] < out["globex_low"])
    out["max_extension_beyond_globex_range"] = pd.concat(
        [
            (out["rth_morning_high"] - out["globex_high"]).clip(lower=0),
            (out["globex_low"] - out["rth_morning_low"]).clip(lower=0),
        ],
        axis=1,
    ).max(axis=1)
    inside_close = (out["rth_morning_close"] <= out["globex_high"]) & (out["rth_morning_close"] >= out["globex_low"])
    out["failed_breakout_reentry"] = (out["breached_globex_high"] | out["breached_globex_low"]) & inside_close
    out["year"] = pd.to_datetime(out["session_date"]).dt.year
    out["month"] = pd.to_datetime(out["session_date"]).dt.strftime("%Y-%m")
    out["week"] = pd.to_datetime(out["session_date"]).dt.strftime("%G-W%V")
    return out


def summarize(part: pd.DataFrame, state_label: str) -> dict[str, Any]:
    if part.empty:
        return {
            "state": state_label,
            "days": 0,
            "mean_rth_morning_range": 0.0,
            "median_rth_morning_range": 0.0,
            "mean_rth_morning_range_div_atr20": 0.0,
            "median_rth_morning_range_div_atr20": 0.0,
            "mean_trendiness": 0.0,
            "median_trendiness": 0.0,
            "mean_signed_trendiness": 0.0,
            "median_signed_trendiness": 0.0,
            "breached_globex_high_rate": 0.0,
            "breached_globex_low_rate": 0.0,
            "closed_outside_globex_range_rate": 0.0,
            "failed_breakout_reentry_rate": 0.0,
            "mean_max_extension_beyond_globex_range": 0.0,
            "median_max_extension_beyond_globex_range": 0.0,
        }
    return {
        "state": state_label,
        "days": int(len(part)),
        "mean_rth_morning_range": float(part["rth_morning_range"].mean()),
        "median_rth_morning_range": float(part["rth_morning_range"].median()),
        "mean_rth_morning_range_div_atr20": float(part["rth_morning_range_div_atr20"].mean()),
        "median_rth_morning_range_div_atr20": float(part["rth_morning_range_div_atr20"].median()),
        "mean_trendiness": float(part["rth_morning_trendiness"].mean()),
        "median_trendiness": float(part["rth_morning_trendiness"].median()),
        "mean_signed_trendiness": float(part["rth_morning_signed_trendiness"].mean()),
        "median_signed_trendiness": float(part["rth_morning_signed_trendiness"].median()),
        "breached_globex_high_rate": float(part["breached_globex_high"].mean()),
        "breached_globex_low_rate": float(part["breached_globex_low"].mean()),
        "closed_outside_globex_range_rate": float(part["closed_outside_globex_range"].mean()),
        "failed_breakout_reentry_rate": float(part["failed_breakout_reentry"].mean()),
        "mean_max_extension_beyond_globex_range": float(part["max_extension_beyond_globex_range"].mean()),
        "median_max_extension_beyond_globex_range": float(part["max_extension_beyond_globex_range"].median()),
    }


def state_summary(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["globex_state"] != "unclassified"].copy()
    for root, root_part in x.groupby("root"):
        total = len(root_part)
        for state in ["compression", "neutral", "expansion"]:
            part = root_part[root_part["globex_state"] == state]
            rows.append({
                "root": root,
                "globex_state": state,
                "days": int(len(part)),
                "share": float(len(part) / total) if total else 0.0,
                "mean_globex_range": float(part["globex_range"].mean()) if len(part) else 0.0,
                "median_globex_range": float(part["globex_range"].median()) if len(part) else 0.0,
                "mean_globex_range_ratio": float(part["globex_range_ratio"].mean()) if len(part) else 0.0,
                "median_globex_range_ratio": float(part["globex_range_ratio"].median()) if len(part) else 0.0,
            })
    return pd.DataFrame(rows)


def outcomes_by_state(table: pd.DataFrame, cohort: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["globex_state"] != "unclassified"].copy()
    for root, root_part in x.groupby("root"):
        rows.append({"root": root, "cohort": cohort, **summarize(root_part, "unconditional")})
        for state in ["compression", "neutral", "expansion"]:
            rows.append({"root": root, "cohort": cohort, **summarize(root_part[root_part["globex_state"] == state], state)})
    return pd.DataFrame(rows)


def bin_diagnostics(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["globex_range_ratio_bin"].notna()].copy()
    for (root, bin_name), part in x.groupby(["root", "globex_range_ratio_bin"], observed=False):
        rows.append({"root": root, "globex_range_ratio_bin": str(bin_name), **summarize(part, str(bin_name))})
    return pd.DataFrame(rows)


def year_splits(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    x = table[table["globex_state"] != "unclassified"].copy()
    for (root, year), root_year in x.groupby(["root", "year"]):
        rows.append({"root": root, "year": int(year), **summarize(root_year, "unconditional")})
        for state in ["compression", "neutral", "expansion"]:
            rows.append({"root": root, "year": int(year), **summarize(root_year[root_year["globex_state"] == state], state)})
    return pd.DataFrame(rows)


def breakout_metrics(table: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "root", "cohort", "state", "days", "breached_globex_high_rate", "breached_globex_low_rate",
        "closed_outside_globex_range_rate", "failed_breakout_reentry_rate",
        "mean_max_extension_beyond_globex_range", "median_max_extension_beyond_globex_range",
    ]
    return outcomes_by_state(table, table["cohort"].iloc[0] if len(table) else "").reindex(columns=cols)


def stability_checks(table: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, bool, list[str]]:
    x = table[table["globex_state"] != "unclassified"].copy()
    base = outcomes_by_state(x, x["cohort"].iloc[0] if len(x) else "primary")
    reasons: list[str] = []
    rows: list[dict[str, Any]] = []
    gates = cfg["phase1_gates"]

    for root, root_part in x.groupby("root"):
        base_root = base[(base["root"] == root) & (base["state"] == "unconditional")].iloc[0]
        base_range = float(base_root["median_rth_morning_range_div_atr20"])
        base_break = float(base_root["closed_outside_globex_range_rate"])
        for state in ["compression", "expansion"]:
            part = root_part[root_part["globex_state"] == state]
            state_row = base[(base["root"] == root) & (base["state"] == state)].iloc[0]
            years_ok = int(
                part.groupby("year").size().reset_index(name="days").query("days >= @gates['min_days_per_state_per_year']")["year"].nunique()
            )
            range_lift = float(state_row["median_rth_morning_range_div_atr20"]) - base_range
            break_lift = float(state_row["closed_outside_globex_range_rate"]) - base_break
            month_counts = part.groupby("month").size().sort_values(ascending=False)
            week_counts = part.groupby("week").size().sort_values(ascending=False)
            largest_month_share = float(month_counts.iloc[0] / len(part)) if len(part) and len(month_counts) else 0.0
            largest_week_share = float(week_counts.iloc[0] / len(part)) if len(part) and len(week_counts) else 0.0
            sparse = len(part) < int(gates["min_days_per_primary_state"])
            unstable = years_ok < int(gates["min_years_with_primary_states"])
            materially_separates = (
                abs(range_lift) >= float(gates["min_morning_range_ratio_lift"])
                or abs(break_lift) >= float(gates["min_breakout_rate_lift"])
            )
            if sparse:
                reasons.append(f"{root}:{state}_too_sparse:{len(part)}")
            if unstable:
                reasons.append(f"{root}:{state}_not_stable_across_years:{years_ok}")
            if not materially_separates:
                reasons.append(f"{root}:{state}_does_not_materially_separate_range_or_breakout")
            rows.append({
                "root": root,
                "state": state,
                "days": int(len(part)),
                "years_with_min_rows": years_ok,
                "median_range_div_atr20_lift_vs_unconditional": range_lift,
                "closed_outside_rate_lift_vs_unconditional": break_lift,
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


def write_source_lineage(out: Path, cfg: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    windows = cfg["session_windows"]
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
        f"Globex context is `{windows['globex_start']}` prior local date through `{windows['globex_end']}` current local date, assigned to the current RTH session date.",
        f"RTH morning target is `{windows['rth_morning_start']}` through `{windows['rth_morning_end']}` on the same local session date.",
        "",
        "## Metric Definitions",
        "",
        "- `breached_Globex_high`: RTH morning high is above the completed Globex high.",
        "- `breached_Globex_low`: RTH morning low is below the completed Globex low.",
        "- `closed_outside_Globex_range`: RTH morning close is outside the completed Globex high/low range.",
        "- `max_extension_beyond_Globex_range`: max positive extension above Globex high or below Globex low during RTH morning.",
        "- `failed_breakout_reentry`: RTH morning breaches either Globex boundary and closes back inside the completed Globex range.",
        "",
        "## Data Windows",
        "",
        f"Primary Databento window: `{cfg['primary_date_filter']['start']}` through `{cfg['primary_date_filter']['end']}`.",
        f"Supplemental Databento window: `{cfg['supplemental_date_filter']['start']}` through `{cfg['supplemental_date_filter']['end']}` when requested.",
        "Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.",
        "",
        "## Lookahead Guard",
        "",
        "Globex state uses only completed Globex bars and a rolling median over prior completed Globex sessions. RTH morning outcomes are measured after the 09:30 open and are not used for state classification.",
    ]
    (out / "source_lineage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verdict(out: Path, cfg: dict[str, Any], verdict: str, reasons: list[str]) -> None:
    lines = [
        "# Coiled Spring Globex -> RTH Morning Verdict",
        "",
        f"Issue: {cfg['issue_url']}",
        f"Parent roadmap: {cfg['parent_issue_url']}",
        "",
        f"Verdict: `{verdict}`",
        "",
        "This is a Phase 1 state-variable audit only. It does not run strategy signals and cannot approve paper/live trading.",
        "",
        "## Interpretation",
        "",
    ]
    if verdict == "session_regime_proxy_rejected":
        lines += [
            "- Completed Globex range state did not pass the Phase 1 state-variable gate.",
            "- The result should not be used to open a signal diagnostic without a separate review.",
        ]
    else:
        lines += [
            "- Completed Globex range state shows enough diagnostic separation to continue research, but remains non-tradable by itself.",
            "- Any signal test must be opened as a separate issue.",
        ]
    lines += [
        "",
        "Gate reasons:",
    ]
    lines += [f"- {reason}" for reason in reasons] or ["- none"]
    lines += [
        "",
        "Guardrails:",
        "- No Donchian or other strategy signal was run.",
        "- No paper/live approval.",
        "- No NinjaTrader execution.",
        "- No broker/IBKR work.",
        "- No primary validation candidate.",
    ]
    (out / "VERDICT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_top_report(date: str, out: Path, verdict: str) -> Path:
    target = Path(f"COILED_SPRING_GLOBEX_RTH_MORNING_{date}.md")
    text = [(out / "VERDICT.md").read_text(encoding="utf-8").rstrip(), ""]
    summary_path = out / "rth_morning_outcomes_by_globex_state.csv"
    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        key = summary[(summary["state"].isin(["unconditional", "compression", "neutral", "expansion"]))]
        text += [
            "## Primary Summary",
            "",
            "| Root | State | Days | Median RTH morning range / ATR20 | Closed outside Globex rate | Failed breakout reentry rate |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for row in key.to_dict("records"):
            text.append(
                f"| {row['root']} | {row['state']} | {row['days']} | {float(row['median_rth_morning_range_div_atr20']):.3f} | {float(row['closed_outside_globex_range_rate']):.3f} | {float(row['failed_breakout_reentry_rate']):.3f} |"
            )
        text += [
            "",
            "## Artifacts",
            "",
            f"- Report directory: `{repo_rel(out)}`",
            "- Required tables: `globex_state_summary.csv`, `rth_morning_outcomes_by_globex_state.csv`, `breakout_reentry_metrics.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.",
            f"- Final verdict: `{verdict}`.",
            "",
        ]
    target.write_text("\n".join(text), encoding="utf-8")
    return target


def prepare_output_dir(out: Path, force: bool) -> None:
    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f"{out} exists and is non-empty; pass --force")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    out = args.out_dir or Path(f"reports/coiled_spring_globex_rth_morning_{args.date}")
    prepare_output_dir(out, args.force)

    primary_path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
    full = read_ohlcv(primary_path, cfg, "databento_ohlcv_1m")
    sources = [source_info(full, "databento_ohlcv_1m_full_view", primary_path, "primary_and_supplemental_source")]
    primary = build_session_table(full, cfg, cfg["primary_date_filter"], "primary_2023_2025")
    primary.to_csv(out / "session_state_table.csv", index=False)
    state_summary(primary).to_csv(out / "globex_state_summary.csv", index=False)
    outcomes_by_state(primary, "primary_2023_2025").to_csv(out / "rth_morning_outcomes_by_globex_state.csv", index=False)
    breakout_metrics(primary).to_csv(out / "breakout_reentry_metrics.csv", index=False)
    year_splits(primary).to_csv(out / "year_splits.csv", index=False)
    bin_diagnostics(primary).to_csv(out / "diagnostic_bin_grid.csv", index=False)
    stability, gate_ok, reasons = stability_checks(primary, cfg)
    stability.to_csv(out / "stability_checks.csv", index=False)

    if args.include_supplemental:
        supp = build_session_table(full, cfg, cfg["supplemental_date_filter"], "supplemental_2026_q1")
        supplemental_or_parity(supp, "supplemental_2026_q1").to_csv(out / "supplemental_2026_q1.csv", index=False)
    else:
        pd.DataFrame([{"status": "not_requested"}]).to_csv(out / "supplemental_2026_q1.csv", index=False)

    if args.local_parity:
        local_path = Path(cfg["data_sources"].get("local_ninja_ohlcv_1m", ""))
        if local_path.exists():
            local = read_ohlcv(local_path, cfg, "local_ninja_ohlcv_1m")
            sources.append(source_info(local, "local_ninja_ohlcv_1m", local_path, "under_sampled_recency_sanity_only"))
            local_window = {
                "start": str(add_local_time(local, cfg)["local_date"].min()),
                "end": str(add_local_time(local, cfg)["local_date"].max()),
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
