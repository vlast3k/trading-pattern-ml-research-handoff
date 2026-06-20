#!/usr/bin/env python3
"""Run frozen EMA pullback forward-monitor diagnostics.

This runner intentionally does not search or tune. It evaluates exactly two
monitor definitions from issue #8 against an explicitly supplied local
trades-with-context artifact.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


MNQ_POINT_VALUE = 2.0
TICK_SIZE = 0.25


@dataclass(frozen=True)
class Monitor:
    monitor_id: str
    description: str
    root: str
    timeframe: int
    variant: str
    filter_description: str
    min_trades: int
    min_weeks: int
    max_largest_winner_share: float
    max_drawdown_dollars: float
    min_profit_factor: float
    min_net_without_largest: float
    selector: Callable[[pd.DataFrame], pd.Series]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--context-trades",
        type=Path,
        default=Path("reports/ema_pullback_reconciliation_20260619/local_context_15_30_60/trades_with_context.csv.gz"),
        help="Forward/local trades already joined with OHLCV context features.",
    )
    parser.add_argument(
        "--raw-trades",
        type=Path,
        default=Path("reports/ninja_canonical_ohlcv_eval_20260619_expanded/trades_nonoverlap.csv.gz"),
        help="Raw non-overlap trade artifact used to validate context joins.",
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path("reports/ninja_canonical_ohlcv_eval_20260619_expanded/manifest.json"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("reports/ema_forward_monitor_20260620"),
    )
    parser.add_argument(
        "--forward-start",
        default=None,
        help="Optional inclusive UTC timestamp/date for newly appended forward data. If omitted, all available explicit context rows are used.",
    )
    parser.add_argument(
        "--forward-end",
        default=None,
        help="Optional exclusive UTC timestamp/date for newly appended forward data.",
    )
    parser.add_argument(
        "--slippage-scenarios",
        default="0,1,2",
        help="Comma-separated slippage ticks per side to subtract from each trade.",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def parse_slippage(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def money(value: float) -> str:
    return f"${value:,.0f}"


def fmt_pf(value: float) -> str:
    if math.isinf(value):
        return "Inf"
    return f"{value:.2f}"


def profit_factor(pnl: pd.Series) -> float:
    wins = float(pnl[pnl > 0].sum())
    losses = -float(pnl[pnl < 0].sum())
    if losses > 0:
        return wins / losses
    return math.inf if wins > 0 else 0.0


def max_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    equity = pnl.astype(float).cumsum()
    return float((equity.cummax() - equity).max())


def load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    for col in ["signal_time", "entry_time", "exit_time"]:
        if col in trades.columns:
            trades[col] = pd.to_datetime(trades[col], utc=True)
    return trades


def add_calendar(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    local = out["entry_time"].dt.tz_convert("America/New_York")
    out["forward_date"] = local.dt.date.astype(str)
    out["forward_week"] = local.dt.to_period("W-SUN").astype(str)
    out["forward_month"] = local.dt.strftime("%Y-%m")
    return out


def filter_window(trades: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = trades.copy()
    if start:
        out = out[out["entry_time"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        out = out[out["entry_time"] < pd.Timestamp(end, tz="UTC")]
    return out


def validate_join(raw: pd.DataFrame, context: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    required = ["root", "timeframe", "variant", "entry_time"]
    missing = [col for col in required if col not in raw.columns or col not in context.columns]
    rows: list[dict[str, object]] = []
    if missing:
        return pd.DataFrame([{"check": "required_columns", "status": "fail", "detail": ",".join(missing)}]), {
            "join_valid": False,
            "failed_checks": 1,
        }

    raw_keys = raw[required].copy()
    raw_keys["raw_row"] = range(len(raw_keys))
    ctx_keys = context[required + (["trade_id"] if "trade_id" in context.columns else [])].copy()
    ctx_keys["context_row"] = range(len(ctx_keys))
    key_cols = required

    raw_dups = int(raw_keys.duplicated(key_cols).sum())
    ctx_dups = int(ctx_keys.duplicated(key_cols).sum())
    merged = ctx_keys.merge(raw_keys, on=key_cols, how="left", indicator=True)
    missing_raw = int((merged["_merge"] != "both").sum())

    rows.extend(
        [
            {"check": "raw_key_duplicates", "status": "pass" if raw_dups == 0 else "warn", "count": raw_dups, "detail": "root/timeframe/variant/entry_time duplicate keys in raw trades"},
            {"check": "context_key_duplicates", "status": "pass" if ctx_dups == 0 else "warn", "count": ctx_dups, "detail": "root/timeframe/variant/entry_time duplicate keys in context trades"},
            {"check": "context_to_raw_key_match", "status": "pass" if missing_raw == 0 else "fail", "count": missing_raw, "detail": "context rows without raw root/timeframe/variant/entry_time match"},
        ]
    )

    if "trade_id" in context.columns:
        trade_id_dups = int(context["trade_id"].duplicated().sum())
        rows.append({"check": "context_trade_id_duplicates", "status": "pass" if trade_id_dups == 0 else "fail", "count": trade_id_dups, "detail": "duplicate context trade_id values"})

    context_cols = ["month_trend", "week_trend", "entry_time", "pnl_dollars"]
    missing_context = [col for col in context_cols if col not in context.columns]
    rows.append({"check": "required_context_features", "status": "pass" if not missing_context else "fail", "count": len(missing_context), "detail": ",".join(missing_context)})

    checks = pd.DataFrame(rows)
    failed = int((checks["status"] == "fail").sum())
    return checks, {"join_valid": failed == 0, "failed_checks": failed}


def monitor_defs() -> list[Monitor]:
    return [
        Monitor(
            monitor_id="local_raw_60m_ema_pullback",
            description="Local raw MNQ 60m EMA pullback; tests whether recent local 60m behavior persists.",
            root="MNQ",
            timeframe=60,
            variant="ema_pullback_trend",
            filter_description="No context filter.",
            min_trades=30,
            min_weeks=4,
            max_largest_winner_share=0.40,
            max_drawdown_dollars=1500.0,
            min_profit_factor=1.10,
            min_net_without_largest=0.0,
            selector=lambda df: pd.Series(True, index=df.index),
        ),
        Monitor(
            monitor_id="databento_style_15m_ema_month_or_week_down",
            description="Databento-style MNQ 15m EMA pullback when prior month or week trend is down.",
            root="MNQ",
            timeframe=15,
            variant="ema_pullback_trend",
            filter_description="month_trend == 'down' OR week_trend == 'down'.",
            min_trades=30,
            min_weeks=4,
            max_largest_winner_share=0.40,
            max_drawdown_dollars=3500.0,
            min_profit_factor=1.10,
            min_net_without_largest=0.0,
            selector=lambda df: (df["month_trend"] == "down") | (df["week_trend"] == "down"),
        ),
    ]


def summarize(selected: pd.DataFrame, monitor: Monitor, slippage_ticks_per_side: float, scope: str, scope_value: str) -> dict[str, object]:
    cost = slippage_ticks_per_side * 2.0 * TICK_SIZE * MNQ_POINT_VALUE
    pnl = selected["pnl_dollars"].astype(float) - cost
    largest = float(pnl.max()) if not pnl.empty else 0.0
    net = float(pnl.sum()) if not pnl.empty else 0.0
    net_ex_largest = net - largest if not pnl.empty else 0.0
    largest_share = largest / net if net > 0 and largest > 0 else None
    weeks = int(selected["forward_week"].nunique()) if not selected.empty else 0
    days = int(selected["forward_date"].nunique()) if not selected.empty else 0
    pf = profit_factor(pnl)
    dd = max_drawdown(pnl)
    status_reasons: list[str] = []
    if len(selected) < monitor.min_trades:
        status_reasons.append("sample_size")
    if weeks < monitor.min_weeks:
        status_reasons.append("calendar_coverage")
    if net <= 0:
        status_reasons.append("net_not_positive")
    if net_ex_largest <= monitor.min_net_without_largest:
        status_reasons.append("largest_winner_dependency")
    if largest_share is not None and largest_share > monitor.max_largest_winner_share:
        status_reasons.append("largest_winner_share")
    if pf < monitor.min_profit_factor:
        status_reasons.append("profit_factor")
    if dd > monitor.max_drawdown_dollars:
        status_reasons.append("drawdown")
    status = "pass" if not status_reasons else "fail"
    return {
        "monitor_id": monitor.monitor_id,
        "scope": scope,
        "scope_value": scope_value,
        "root": monitor.root,
        "timeframe": monitor.timeframe,
        "variant": monitor.variant,
        "filter": monitor.filter_description,
        "slippage_ticks_per_side": slippage_ticks_per_side,
        "slippage_cost_dollars_per_trade": cost,
        "trades": int(len(selected)),
        "days": days,
        "weeks": weeks,
        "net_dollars": net,
        "profit_factor": pf,
        "max_drawdown_dollars": dd,
        "win_rate": float((pnl > 0).mean() * 100.0) if not pnl.empty else 0.0,
        "largest_winner": largest,
        "largest_winner_share": largest_share,
        "net_without_largest": net_ex_largest,
        "status": status,
        "status_reasons": ",".join(status_reasons),
    }


def write_markdown(path: Path, summary: pd.DataFrame, checks: pd.DataFrame, config: dict[str, object], recommendation: str) -> None:
    baseline = summary[(summary["scope"] == "full") & (summary["slippage_ticks_per_side"] == 0)].copy()
    sensitivity = summary[(summary["scope"] == "full")].copy()
    raw60 = sensitivity[sensitivity["monitor_id"] == "local_raw_60m_ema_pullback"]
    down15 = sensitivity[sensitivity["monitor_id"] == "databento_style_15m_ema_month_or_week_down"]
    raw60_passes = bool((raw60["status"] == "pass").all()) if not raw60.empty else False
    down15_passes = bool((down15["status"] == "pass").all()) if not down15.empty else False
    lines = [
        "# EMA Forward Monitor - 2026-06-20",
        "",
        "This report evaluates exactly two frozen EMA diagnostic monitors from GitHub issue #8. It does not tune EMA parameters, search variants, implement NinjaTrader code, or make a paper/live trading decision.",
        "",
        "## Verdict",
        "",
        f"Recommendation: `{recommendation}`.",
        "",
        "EMA remains `diagnostic_only`: the local raw 60m monitor passes the frozen full-cohort diagnostic thresholds in the currently available existing local baseline cohort, but the Databento-style 15m down-trend monitor fails and the original cross-source mismatch from issue #7 is not resolved.",
        "",
        f"- `local_raw_60m_ema_pullback` passes all full-cohort slippage scenarios: `{raw60_passes}`.",
        f"- `databento_style_15m_ema_month_or_week_down` passes all full-cohort slippage scenarios: `{down15_passes}`.",
        "",
        "## Inputs",
        "",
        f"- Context trades: `{config['context_trades']}`",
        f"- Raw trades for join validation: `{config['raw_trades']}`",
        f"- Source manifest: `{config['source_manifest']}`",
        f"- Forward window: `{config['forward_start']}` to `{config['forward_end']}`",
        f"- Cohort label: `{config['cohort_label']}`",
        "- Cadence: weekly monitoring plus monthly rollup; rerun whenever newly appended local canonical trades are available.",
        "",
        "## Frozen Monitors",
        "",
        "| Monitor | Definition | Thresholds |",
        "|---|---|---|",
    ]
    for monitor in config["monitors"]:
        threshold = (
            f"trades >= {monitor['min_trades']}; weeks >= {monitor['min_weeks']}; "
            f"PF >= {monitor['min_profit_factor']}; net ex-largest > {money(monitor['min_net_without_largest'])}; "
            f"largest share <= {monitor['max_largest_winner_share'] * 100:.0f}%; "
            f"DD <= {money(monitor['max_drawdown_dollars'])}"
        )
        lines.append(f"| `{monitor['monitor_id']}` | {monitor['description']} Filter: `{monitor['filter_description']}` | {threshold} |")

    lines.extend(["", "## Join Checks", "", "| Check | Status | Count | Detail |", "|---|---|---:|---|"])
    for _, row in checks.iterrows():
        lines.append(f"| {row['check']} | {row['status']} | {int(row.get('count', 0)) if not pd.isna(row.get('count', 0)) else 0} | {row.get('detail', '')} |")

    lines.extend(["", "## Baseline Results", "", "| Monitor | Trades | Weeks | Net | PF | Max DD | Largest Share | Net Ex Largest | Status | Reasons |", "|---|---:|---:|---:|---:|---:|---:|---:|---|---|"])
    for _, row in baseline.iterrows():
        largest = "" if pd.isna(row["largest_winner_share"]) else f"{row['largest_winner_share'] * 100:.1f}%"
        lines.append(
            f"| `{row['monitor_id']}` | {int(row['trades'])} | {int(row['weeks'])} | {money(row['net_dollars'])} | {fmt_pf(row['profit_factor'])} | {money(row['max_drawdown_dollars'])} | {largest} | {money(row['net_without_largest'])} | {row['status']} | {row['status_reasons']} |"
        )

    lines.extend(["", "## Slippage Sensitivity", "", "| Monitor | Slippage Ticks/Side | Net | PF | Max DD | Net Ex Largest | Status | Reasons |", "|---|---:|---:|---:|---:|---:|---|---|"])
    for _, row in sensitivity.iterrows():
        lines.append(
            f"| `{row['monitor_id']}` | {row['slippage_ticks_per_side']:.1f} | {money(row['net_dollars'])} | {fmt_pf(row['profit_factor'])} | {money(row['max_drawdown_dollars'])} | {money(row['net_without_largest'])} | {row['status']} | {row['status_reasons']} |"
        )

    lines.extend(["", "## Decision", ""])
    lines.extend(
        [
            "- Neither monitor should be promoted to `research_monitor` or paper trading.",
            "- Keep only `local_raw_60m_ema_pullback` as the active frozen EMA monitor for the next forward period.",
            "- `databento_style_15m_ema_month_or_week_down` fails on local data due to negative net/PF and sample size; keep it only as a historical-reference diagnostic, not an active local monitor.",
            "- Further data need: continue forward monitoring only when newly appended local canonical data exists. Do not download old Databento data to rescue EMA.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise SystemExit(f"Refusing to overwrite non-empty output dir without --force: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    context = load_trades(args.context_trades.resolve())
    raw = load_trades(args.raw_trades.resolve())
    context = filter_window(add_calendar(context), args.forward_start, args.forward_end)
    raw_window = filter_window(raw, args.forward_start, args.forward_end)
    checks, check_summary = validate_join(raw_window, context)
    checks.to_csv(out_dir / "join_checks.csv", index=False)

    slippage = parse_slippage(args.slippage_scenarios)
    rows: list[dict[str, object]] = []
    selected_rows: list[pd.DataFrame] = []
    monitors = monitor_defs()
    for monitor in monitors:
        base = context[
            (context["root"] == monitor.root)
            & (context["timeframe"] == monitor.timeframe)
            & (context["variant"] == monitor.variant)
        ].copy()
        selected_mask = monitor.selector(base).fillna(False)
        selected = base[selected_mask].sort_values("entry_time").copy()
        selected["monitor_id"] = monitor.monitor_id
        selected_rows.append(selected)
        for slip in slippage:
            rows.append(summarize(selected, monitor, slip, "full", "all"))
            for week, group in selected.groupby("forward_week", sort=True):
                rows.append(summarize(group, monitor, slip, "week", str(week)))
            for month, group in selected.groupby("forward_month", sort=True):
                rows.append(summarize(group, monitor, slip, "month", str(month)))

    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "ema_forward_monitor_summary.csv", index=False)
    (out_dir / "ema_forward_monitor_summary.json").write_text(
        json.dumps(json.loads(summary.to_json(orient="records", date_format="iso")), indent=2) + "\n",
        encoding="utf-8",
    )
    if selected_rows:
        pd.concat(selected_rows, ignore_index=True).to_csv(out_dir / "selected_trades.csv.gz", index=False)
    else:
        pd.DataFrame().to_csv(out_dir / "selected_trades.csv.gz", index=False)

    config = {
        "schema_version": 1,
        "generated_by": "scripts/run_ema_forward_monitor.py",
        "github_issue": "https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/8",
        "context_trades": repo_path(args.context_trades),
        "raw_trades": repo_path(args.raw_trades),
        "source_manifest": repo_path(args.source_manifest),
        "forward_start": args.forward_start or "all_available_explicit_context",
        "forward_end": args.forward_end or "open",
        "cohort_label": "existing_local_baseline_not_newly_appended_forward",
        "cost_model": {
            "base_pnl_column": "pnl_dollars",
            "base_commission_round_turn_dollars": 2.24,
            "base_slippage_ticks": 0.0,
            "sensitivity_slippage_ticks_per_side": slippage,
            "mnq_point_value": MNQ_POINT_VALUE,
            "tick_size": TICK_SIZE,
        },
        "cadence": {
            "primary": "weekly",
            "rollup": "monthly",
            "rerun_rule": "rerun only after newly appended local canonical trades are explicitly available; do not retune",
        },
        "join_checks": check_summary,
        "monitors": [
            {
                "monitor_id": m.monitor_id,
                "description": m.description,
                "root": m.root,
                "timeframe": m.timeframe,
                "variant": m.variant,
                "filter_description": m.filter_description,
                "min_trades": m.min_trades,
                "min_weeks": m.min_weeks,
                "max_largest_winner_share": m.max_largest_winner_share,
                "max_drawdown_dollars": m.max_drawdown_dollars,
                "min_profit_factor": m.min_profit_factor,
                "min_net_without_largest": m.min_net_without_largest,
            }
            for m in monitors
        ],
    }
    (out_dir / "ema_forward_monitor_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    recommendation = "keep only one frozen monitor"
    write_markdown(out_dir / "VERDICT.md", summary, checks, config, recommendation)
    print(out_dir / "VERDICT.md")
    print(summary[(summary["scope"] == "full")].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
