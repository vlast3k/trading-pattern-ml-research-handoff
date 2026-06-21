#!/usr/bin/env python3
"""Run frozen Donchian forward/local validation for issue #11.

The runner is intentionally lineage-first. If a true post-selection forward
cohort exists, it runs forward validation. Otherwise it audits the available
local frozen-registry evidence and labels it as such.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


MNQ_POINT_VALUE = 2.0
TICK_SIZE = 0.25


@dataclass(frozen=True)
class Candidate:
    candidate_id: str = "mnq_60_donchian_confluence_ge6"
    family: str = "donchian_breakout"
    root: str = "MNQ"
    timeframe: int = 60
    variant: str = "donchian_breakout"
    selector_column: str = "confluence_score"
    selector_op: str = ">="
    selector_value: float = 6.0
    status_entering_issue: str = "primary_validation_candidate"
    formula: str = "20-bar prior high/low Donchian breakout; ATR(14) * 1.10 stop; reward/risk 2.0; max hold 20 bars."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/local_canonical/donchian_forward_20260620"),
        help="Repo-relative data package root.",
    )
    parser.add_argument(
        "--forward-trades",
        type=Path,
        default=Path("data/local_canonical/donchian_forward_20260620/forward_trades/trades_with_context.csv.gz"),
        help="Required forward/local trades-with-context input not used to select the candidate.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
    )
    parser.add_argument("--slippage-scenarios", default="0,1,2")
    parser.add_argument("--commission-round-turn", type=float, default=2.24)
    parser.add_argument("--min-weeks", type=int, default=4)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def is_repo_relative(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path.cwd().resolve())
        return True
    except ValueError:
        return False


def git_ignored(path: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", repo_path(path)],
            cwd=Path.cwd(),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    return result.returncode == 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_row_count(path: Path) -> int | None:
    try:
        opener = gzip.open if path.name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", newline="") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    except Exception:  # noqa: BLE001
        return None


def inspect_table(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": repo_path(path),
        "exists": path.exists(),
        "repo_relative": is_repo_relative(path),
    }
    if not path.exists():
        return info
    if path.is_dir():
        info.update(
            {
                "kind": "directory",
                "file_count": sum(1 for child in path.rglob("*") if child.is_file()),
                "git_ignored": git_ignored(path),
            }
        )
        return info
    info.update(
        {
            "kind": "file",
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
            "git_ignored": git_ignored(path),
        }
    )
    if path.suffix == ".csv" or path.name.endswith(".csv.gz"):
        info["row_count"] = csv_row_count(path)
        try:
            sample = pd.read_csv(path)
            info["columns"] = list(sample.columns)
            for column in ["entry_time", "signal_time", "exit_time", "ts_event"]:
                if column in sample.columns:
                    timestamps = pd.to_datetime(sample[column], utc=True, errors="coerce").dropna()
                    if not timestamps.empty:
                        info[f"{column}_first"] = timestamps.min().isoformat()
                        info[f"{column}_last"] = timestamps.max().isoformat()
        except Exception as exc:  # noqa: BLE001
            info["inspection_error"] = str(exc)
    return info


def parse_slippage(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def profit_factor(pnl: pd.Series) -> float:
    wins = float(pnl[pnl > 0].sum())
    losses = -float(pnl[pnl < 0].sum())
    if losses > 0:
        return wins / losses
    return math.inf if wins > 0 else 0.0


def max_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    equity = pd.concat([pd.Series([0.0]), pnl.astype(float).cumsum()], ignore_index=True)
    return float((equity.cummax() - equity).max())


def money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"${float(value):,.0f}"


def fmt_pf(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    number = float(value)
    return "Inf" if math.isinf(number) else f"{number:.2f}"


def add_calendar(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True, errors="coerce")
    local = out["entry_time"].dt.tz_convert("America/New_York")
    out["forward_date"] = local.dt.date.astype(str)
    out["forward_week"] = local.dt.tz_localize(None).dt.to_period("W-SUN").astype(str)
    return out


def select_candidate(trades: pd.DataFrame, candidate: Candidate) -> pd.DataFrame:
    required = ["root", "timeframe", "variant", "entry_time", "pnl_dollars", candidate.selector_column]
    missing = [column for column in required if column not in trades.columns]
    if missing:
        raise ValueError(f"missing required columns: {','.join(missing)}")
    mask = (
        (trades["root"] == candidate.root)
        & (pd.to_numeric(trades["timeframe"], errors="coerce") == candidate.timeframe)
        & (trades["variant"] == candidate.variant)
        & (pd.to_numeric(trades[candidate.selector_column], errors="coerce") >= candidate.selector_value)
    )
    return add_calendar(trades[mask].copy()).sort_values("entry_time")


def select_available_audit_candidate(data_root: Path, candidate: Candidate, checks: list[dict[str, str]], reasons: list[str]) -> tuple[pd.DataFrame, str]:
    reference_trades = data_root / "frozen_registry_reference" / "trades_with_context.csv.gz"
    selected_trade_ids = data_root / "frozen_registry_reference" / "selected_trade_ids.csv.gz"
    if reference_trades.exists() and selected_trade_ids.exists():
        trades = pd.read_csv(reference_trades)
        selector_ids = pd.read_csv(selected_trade_ids)
        selector_rows = selector_ids[selector_ids["selector_id"] == candidate.candidate_id].copy()
        if not selector_rows.empty and "trade_id" in trades.columns:
            selected = selector_rows.merge(trades, on="trade_id", how="left", indicator=True)
            missing = int((selected["_merge"] != "both").sum())
            if missing == 0:
                selected = selected.drop(columns=["_merge"])
                checks.append({"check": "available_audit_exact_selector_id_join", "status": "pass", "detail": f"{candidate.candidate_id}: {len(selected)} trades"})
                return add_calendar(selected).sort_values("entry_time"), "selector_id_join"
            checks.append({"check": "available_audit_exact_selector_id_join", "status": "fail", "detail": f"{missing} selected trade ids did not join"})
            reasons.append(f"{missing} selected trade ids did not join to frozen registry reference trades.")
        else:
            checks.append({"check": "available_audit_exact_selector_id_join", "status": "fail", "detail": "selector id or trade_id mapping unavailable"})
    else:
        checks.append({"check": "available_audit_reference_inputs_exist", "status": "fail", "detail": "missing frozen registry reference trades or selected ids"})

    if reference_trades.exists():
        try:
            trades = pd.read_csv(reference_trades)
            selected = select_candidate(trades, candidate)
            checks.append({"check": "available_audit_selector_filter_fallback", "status": "pass", "detail": f"{len(selected)} trades"})
            reasons.append("Used fallback filter root=MNQ, timeframe=60, variant=donchian_breakout, confluence_score>=6 because exact selector-id mapping was insufficient.")
            return selected, "fallback_filter"
        except Exception as exc:  # noqa: BLE001
            checks.append({"check": "available_audit_selector_filter_fallback", "status": "fail", "detail": str(exc)})
            reasons.append(f"Available-data audit selection failed: {exc}")
    return pd.DataFrame(), "unavailable"


def adjusted_pnl(selected: pd.DataFrame, slippage_ticks_per_side: float, commission: float) -> pd.Series:
    slippage_cost = slippage_ticks_per_side * 2.0 * TICK_SIZE * MNQ_POINT_VALUE
    total_cost = commission + slippage_cost
    return selected["pnl_dollars"].astype(float) - total_cost if not selected.empty else pd.Series(dtype=float)


def summarize(selected: pd.DataFrame, slippage_ticks_per_side: float, commission: float, scope: str, scope_value: str) -> dict[str, Any]:
    slippage_cost = slippage_ticks_per_side * 2.0 * TICK_SIZE * MNQ_POINT_VALUE
    total_cost = commission + slippage_cost
    pnl = adjusted_pnl(selected, slippage_ticks_per_side, commission)
    net = float(pnl.sum()) if not pnl.empty else 0.0
    largest = float(pnl.max()) if not pnl.empty else 0.0
    net_ex_largest = net - largest if not pnl.empty else 0.0
    largest_share = largest / net if net > 0 and largest > 0 else None
    return {
        "scope": scope,
        "scope_value": scope_value,
        "slippage_ticks_per_side": slippage_ticks_per_side,
        "commission_round_turn_dollars": commission,
        "cost_dollars_per_trade": total_cost,
        "trades": int(len(selected)),
        "days": int(selected["forward_date"].nunique()) if not selected.empty else 0,
        "weeks": int(selected["forward_week"].nunique()) if not selected.empty else 0,
        "net_dollars": net,
        "profit_factor": profit_factor(pnl),
        "max_drawdown_dollars": max_drawdown(pnl),
        "largest_winner": largest,
        "largest_winner_share": largest_share,
        "net_without_largest": net_ex_largest,
    }


def concentration(selected: pd.DataFrame, slippage_ticks_per_side: float = 0.0, commission: float = 0.0) -> dict[str, Any]:
    if selected.empty:
        return {"best_day_share": None, "best_week_share": None}
    pnl = adjusted_pnl(selected, slippage_ticks_per_side, commission)
    net = float(pnl.sum())
    if net <= 0:
        return {"best_day_share": None, "best_week_share": None}
    by_day = selected.assign(_pnl=pnl).groupby("forward_date")["_pnl"].sum()
    by_week = selected.assign(_pnl=pnl).groupby("forward_week")["_pnl"].sum()
    return {
        "best_day_share": float(by_day.max() / net),
        "best_week_share": float(by_week.max() / net),
    }


def append_gate_reason(reasons: list[str], text: str) -> None:
    if text not in reasons:
        reasons.append(text)


def evaluate_verdict(baseline: pd.Series, summary: pd.DataFrame, analysis_mode: str, min_trades: int, min_weeks: int, reasons: list[str]) -> str:
    if int(baseline["trades"]) < min_trades:
        append_gate_reason(reasons, f"Only {int(baseline['trades'])} trades; minimum is {min_trades}.")
        return "under_sampled_no_forward_data" if analysis_mode == "available_data_audit" else "under_sampled_continue_monitoring"
    if int(baseline["weeks"]) < min_weeks:
        append_gate_reason(reasons, f"Only {int(baseline['weeks'])} weeks; minimum is {min_weeks}.")
        return "under_sampled_no_forward_data" if analysis_mode == "available_data_audit" else "under_sampled_continue_monitoring"

    failed_gate = False
    if float(baseline["net_dollars"]) <= 0:
        append_gate_reason(reasons, "Net PnL is not positive.")
        failed_gate = True
    if float(baseline["profit_factor"]) < 1.10:
        append_gate_reason(reasons, "Profit factor is below 1.10.")
        failed_gate = True
    if float(baseline["max_drawdown_dollars"]) > 2500:
        append_gate_reason(reasons, "Max drawdown exceeds $2,500.")
        failed_gate = True
    if float(baseline["net_without_largest"]) <= 0:
        append_gate_reason(reasons, "Net PnL excluding the largest winner is not positive.")
        failed_gate = True
    if pd.notna(baseline["largest_winner_share"]) and float(baseline["largest_winner_share"]) >= 0.50:
        append_gate_reason(reasons, "Largest winner explains at least 50% of net profit.")
        failed_gate = True
    if pd.notna(baseline["best_day_share"]) and float(baseline["best_day_share"]) >= 0.50:
        append_gate_reason(reasons, "Best day explains at least 50% of net profit.")
        failed_gate = True
    if pd.notna(baseline["best_week_share"]) and float(baseline["best_week_share"]) >= 0.50:
        append_gate_reason(reasons, "Best week explains at least 50% of net profit.")
        failed_gate = True
    if failed_gate:
        return "fail_demote_to_diagnostic_only"

    two_tick = summary[(summary["scope"] == "full") & (summary["slippage_ticks_per_side"] == 2)]
    if not two_tick.empty and float(two_tick.iloc[0]["profit_factor"]) < 1.05:
        append_gate_reason(reasons, "PF under 2 ticks per side slippage is below 1.05.")
        return "fail_demote_to_diagnostic_only"

    if analysis_mode == "available_data_audit":
        append_gate_reason(reasons, "No true post-selection forward file exists; positive result remains prior/reference/local available-data evidence.")
        return "partial_available_data_audit"
    return "pass_forward_validation"


def write_source_lineage(path: Path, input_manifest: dict[str, Any], verdict: str, reasons: list[str], analysis_mode: str) -> None:
    lines = [
        "# Donchian Validation Source Lineage",
        "",
        f"Analysis mode: `{analysis_mode}`",
        "",
        f"Verdict gate: `{verdict}`",
        "",
        "This artifact documents repo-relative inputs for GitHub issue #11. Large payload files may be ignored by git, but they must exist at the listed repo-relative paths before a trading result can be accepted.",
        "",
        "## Gate Reasons",
        "",
    ]
    lines.extend([f"- {reason}" for reason in reasons] or ["- none"])
    lines.extend(["", "## Inputs", "", "| Role | Path | Exists | Ignored | Rows | First Timestamp | Last Timestamp | SHA-256 |", "|---|---|---:|---:|---:|---|---|---|"])
    for item in input_manifest["inputs"]:
        first = item.get("entry_time_first") or item.get("signal_time_first") or item.get("ts_event_first") or ""
        last = item.get("entry_time_last") or item.get("signal_time_last") or item.get("ts_event_last") or ""
        lines.append(
            f"| {item['role']} | `{item['path']}` | {item.get('exists')} | {item.get('git_ignored')} | {item.get('row_count', '')} | {first} | {last} | `{item.get('sha256', '')}` |"
        )
    lines.extend(["", "## Transfer Rule", "", "To reproduce on another machine, copy the ignored payload files under the same repo-relative `data/local_canonical/donchian_forward_20260620/` directory and keep `IMPORT_MANIFEST.json` in sync."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verdict(path: Path, summary: pd.DataFrame, checks: pd.DataFrame, verdict: str, reasons: list[str], analysis_mode: str, selection_method: str) -> None:
    lines = [
        "# Donchian Validation Verdict",
        "",
        f"Analysis mode: `{analysis_mode}`",
        "",
        f"Verdict: `{verdict}`",
        "",
        "Candidate: `mnq_60_donchian_confluence_ge6`",
        "",
        f"Selection method: `{selection_method}`",
        "",
        "This report does not approve paper/live trading. It is only the issue #11 frozen forward/local validation monitor. In `available_data_audit` mode it is prior/reference/local evidence, not forward validation.",
        "",
        "## Reasons",
        "",
    ]
    lines.extend([f"- {reason}" for reason in reasons] or ["- none"])
    lines.extend(["", "## Join And Lineage Checks", "", "| Check | Status | Detail |", "|---|---|---|"])
    for row in checks.itertuples(index=False):
        lines.append(f"| {row.check} | {row.status} | {row.detail} |")
    lines.extend(["", "## Summary", "", "| Scope | Slippage | Trades | Weeks | Net | PF | Max DD | Largest Share | Best Day | Best Week | Net Ex Largest |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in summary.itertuples(index=False):
        largest = "" if row.largest_winner_share is None or pd.isna(row.largest_winner_share) else f"{row.largest_winner_share * 100:.1f}%"
        best_day = "" if row.best_day_share is None or pd.isna(row.best_day_share) else f"{row.best_day_share * 100:.1f}%"
        best_week = "" if row.best_week_share is None or pd.isna(row.best_week_share) else f"{row.best_week_share * 100:.1f}%"
        lines.append(
            f"| {row.scope}:{row.scope_value} | {row.slippage_ticks_per_side:.1f} | {row.trades} | {row.weeks} | {money(row.net_dollars)} | {fmt_pf(row.profit_factor)} | {money(row.max_drawdown_dollars)} | {largest} | {best_day} | {best_week} | {money(row.net_without_largest)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    candidate = Candidate()
    out_dir = args.out_dir or Path("reports") / f"donchian_forward_validation_{args.date}"
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise SystemExit(f"Refusing to overwrite non-empty output dir without --force: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    data_root = args.data_root
    package_manifest = data_root / "IMPORT_MANIFEST.json"
    reference_trades = data_root / "frozen_registry_reference" / "trades_with_context.csv.gz"
    reference_summary = data_root / "frozen_registry_reference" / "summary.csv"
    selected_trade_ids = data_root / "frozen_registry_reference" / "selected_trade_ids.csv.gz"
    candidate_trades = data_root / "candidate_trades" / "trades_nonoverlap.csv.gz"
    candidate_summary = data_root / "candidate_trades" / "summary_nonoverlap.csv"
    ohlcv_context = data_root / "ohlcv_context" / "front_1m.parquet"
    inputs = [
        ("data_root", data_root),
        ("package_import_manifest", package_manifest),
        ("required_forward_trades", args.forward_trades),
        ("frozen_registry_reference_summary", reference_summary),
        ("frozen_registry_selected_trade_ids", selected_trade_ids),
        ("frozen_registry_reference_trades", reference_trades),
        ("candidate_trades_background_summary", candidate_summary),
        ("candidate_trades_background_source", candidate_trades),
        ("ohlcv_context", ohlcv_context),
    ]
    input_manifest = {
        "schema_version": 1,
        "generated_by": "scripts/run_donchian_forward_validation.py",
        "github_issue": "https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/11",
        "candidate": candidate.__dict__,
        "inputs": [{**inspect_table(path), "role": role} for role, path in inputs],
    }

    checks: list[dict[str, str]] = []
    reasons: list[str] = []
    for item in input_manifest["inputs"]:
        if not item["repo_relative"]:
            checks.append({"check": f"{item['role']}_repo_relative", "status": "fail", "detail": item["path"]})
            reasons.append(f"{item['role']} is not repo-relative")
        elif item["role"] != "required_forward_trades":
            checks.append({"check": f"{item['role']}_repo_relative", "status": "pass", "detail": item["path"]})

    forward_info = next(item for item in input_manifest["inputs"] if item["role"] == "required_forward_trades")
    if forward_info["exists"]:
        analysis_mode = "forward_validation"
        selection_method = "forward_filter"
        checks.append({"check": "required_forward_trades_exists", "status": "pass", "detail": forward_info["path"]})
        trades = pd.read_csv(args.forward_trades)
        try:
            selected = select_candidate(trades, candidate)
            checks.append({"check": "frozen_selector_columns", "status": "pass", "detail": candidate.selector_column})
        except ValueError as exc:
            selected = pd.DataFrame()
            checks.append({"check": "frozen_selector_columns", "status": "fail", "detail": str(exc)})
            reasons.append(str(exc))
    else:
        analysis_mode = "available_data_audit"
        checks.append({"check": "required_forward_trades_exists", "status": "missing_expected_for_audit", "detail": forward_info["path"]})
        reasons.append("True forward trades-with-context file is absent; running available-data audit against frozen registry reference evidence.")
        selected, selection_method = select_available_audit_candidate(data_root, candidate, checks, reasons)

    if selected.empty:
        slippage = parse_slippage(args.slippage_scenarios)
        summary = pd.DataFrame(
            [
                {
                    **summarize(pd.DataFrame(columns=["pnl_dollars", "forward_date", "forward_week"]), slip, args.commission_round_turn, "full", "all"),
                    **concentration(pd.DataFrame(), slip, args.commission_round_turn),
                    "candidate_id": candidate.candidate_id,
                }
                for slip in slippage
            ]
        )
    else:
        rows: list[dict[str, Any]] = []
        for slip in parse_slippage(args.slippage_scenarios):
            rows.append({**summarize(selected, slip, args.commission_round_turn, "full", "all"), **concentration(selected, slip, args.commission_round_turn), "candidate_id": candidate.candidate_id})
            for week, group in selected.groupby("forward_week", sort=True):
                rows.append({**summarize(group, slip, args.commission_round_turn, "week", str(week)), **concentration(group, slip, args.commission_round_turn), "candidate_id": candidate.candidate_id})
            for day, group in selected.groupby("forward_date", sort=True):
                rows.append({**summarize(group, slip, args.commission_round_turn, "day", str(day)), **concentration(group, slip, args.commission_round_turn), "candidate_id": candidate.candidate_id})
        summary = pd.DataFrame(rows)

    baseline = summary[(summary["scope"] == "full") & (summary["slippage_ticks_per_side"] == 0)].iloc[0]
    lineage_failures = [check for check in checks if check["status"] == "fail"]
    if lineage_failures:
        verdict = "incomplete_data_lineage"
        append_gate_reason(reasons, "One or more required package inputs could not be read or reconciled.")
    else:
        verdict = evaluate_verdict(baseline, summary, analysis_mode, args.min_trades, args.min_weeks, reasons)

    config = {
        "schema_version": 1,
        "generated_by": "scripts/run_donchian_forward_validation.py",
        "github_issue": "https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/11",
        "analysis_mode": analysis_mode,
        "selection_method": selection_method,
        "candidate": candidate.__dict__,
        "data_root": repo_path(data_root),
        "forward_trades": repo_path(args.forward_trades),
        "cost_model": {
            "pnl_column": "pnl_dollars",
            "commission_round_turn_dollars": args.commission_round_turn,
            "slippage_ticks_per_side": parse_slippage(args.slippage_scenarios),
            "tick_size": TICK_SIZE,
            "mnq_point_value": MNQ_POINT_VALUE,
        },
        "minimum_evidence": {"trades": args.min_trades, "weeks": args.min_weeks},
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (out_dir / "donchian_forward_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (out_dir / "input_manifest.json").write_text(json.dumps(input_manifest, indent=2) + "\n", encoding="utf-8")
    checks_df = pd.DataFrame(checks)
    checks_df.to_csv(out_dir / "join_checks.csv", index=False)
    summary.to_csv(out_dir / "donchian_forward_summary.csv", index=False)
    selected.to_csv(out_dir / "selected_trades.csv.gz", index=False)
    write_source_lineage(out_dir / "source_lineage.md", input_manifest, verdict, reasons, analysis_mode)
    write_verdict(out_dir / "VERDICT.md", summary, checks_df, verdict, reasons, analysis_mode, selection_method)
    print(out_dir / "VERDICT.md")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
