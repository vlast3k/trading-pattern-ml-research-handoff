#!/usr/bin/env python3
"""Run frozen Donchian forward/local validation for issue #11.

The runner is intentionally lineage-first. It will not treat the prior frozen
registry reference cohort as forward validation data. A valid forward run needs
an explicit repo-relative forward input under the data package.
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
    equity = pnl.astype(float).cumsum()
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
    out["forward_week"] = local.dt.to_period("W-SUN").astype(str)
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


def summarize(selected: pd.DataFrame, slippage_ticks_per_side: float, commission: float, scope: str, scope_value: str) -> dict[str, Any]:
    slippage_cost = slippage_ticks_per_side * 2.0 * TICK_SIZE * MNQ_POINT_VALUE
    total_cost = commission + slippage_cost
    pnl = selected["pnl_dollars"].astype(float) - total_cost if not selected.empty else pd.Series(dtype=float)
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


def concentration(selected: pd.DataFrame) -> dict[str, Any]:
    if selected.empty:
        return {"best_day_share": None, "best_week_share": None}
    pnl = selected["pnl_dollars"].astype(float)
    net = float(pnl.sum())
    if net <= 0:
        return {"best_day_share": None, "best_week_share": None}
    by_day = selected.assign(_pnl=pnl).groupby("forward_date")["_pnl"].sum()
    by_week = selected.assign(_pnl=pnl).groupby("forward_week")["_pnl"].sum()
    return {
        "best_day_share": float(by_day.max() / net),
        "best_week_share": float(by_week.max() / net),
    }


def write_source_lineage(path: Path, input_manifest: dict[str, Any], verdict: str, reasons: list[str]) -> None:
    lines = [
        "# Donchian Forward Validation Source Lineage",
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


def write_verdict(path: Path, summary: pd.DataFrame, checks: pd.DataFrame, verdict: str, reasons: list[str]) -> None:
    lines = [
        "# Donchian Forward Validation Verdict",
        "",
        f"Verdict: `{verdict}`",
        "",
        "Candidate: `mnq_60_donchian_confluence_ge6`",
        "",
        "This report does not approve paper/live trading. It is only the issue #11 frozen forward/local validation monitor.",
        "",
        "## Reasons",
        "",
    ]
    lines.extend([f"- {reason}" for reason in reasons] or ["- none"])
    lines.extend(["", "## Join And Lineage Checks", "", "| Check | Status | Detail |", "|---|---|---|"])
    for row in checks.itertuples(index=False):
        lines.append(f"| {row.check} | {row.status} | {row.detail} |")
    lines.extend(["", "## Summary", "", "| Scope | Slippage | Trades | Weeks | Net | PF | Max DD | Largest Share | Net Ex Largest |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in summary.itertuples(index=False):
        largest = "" if row.largest_winner_share is None or pd.isna(row.largest_winner_share) else f"{row.largest_winner_share * 100:.1f}%"
        lines.append(
            f"| {row.scope}:{row.scope_value} | {row.slippage_ticks_per_side:.1f} | {row.trades} | {row.weeks} | {money(row.net_dollars)} | {fmt_pf(row.profit_factor)} | {money(row.max_drawdown_dollars)} | {largest} | {money(row.net_without_largest)} |"
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
    candidate_trades = data_root / "candidate_trades" / "trades_nonoverlap.csv.gz"
    ohlcv_context = data_root / "ohlcv_context" / "front_1m.parquet"
    inputs = [
        ("data_root", data_root),
        ("package_import_manifest", package_manifest),
        ("required_forward_trades", args.forward_trades),
        ("reference_trades_not_forward", reference_trades),
        ("candidate_trades_context_source", candidate_trades),
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
    if not forward_info["exists"]:
        checks.append({"check": "required_forward_trades_exists", "status": "fail", "detail": forward_info["path"]})
        reasons.append("No eligible forward trades-with-context input exists under the repo-relative data package.")
        selected = pd.DataFrame()
    else:
        checks.append({"check": "required_forward_trades_exists", "status": "pass", "detail": forward_info["path"]})
        trades = pd.read_csv(args.forward_trades)
        try:
            selected = select_candidate(trades, candidate)
            checks.append({"check": "frozen_selector_columns", "status": "pass", "detail": candidate.selector_column})
        except ValueError as exc:
            selected = pd.DataFrame()
            checks.append({"check": "frozen_selector_columns", "status": "fail", "detail": str(exc)})
            reasons.append(str(exc))

    if selected.empty:
        slippage = parse_slippage(args.slippage_scenarios)
        summary = pd.DataFrame(
            [
                {
                    **summarize(pd.DataFrame(columns=["pnl_dollars", "forward_date", "forward_week"]), slip, args.commission_round_turn, "full", "all"),
                    **concentration(pd.DataFrame()),
                    "candidate_id": candidate.candidate_id,
                }
                for slip in slippage
            ]
        )
    else:
        rows: list[dict[str, Any]] = []
        for slip in parse_slippage(args.slippage_scenarios):
            rows.append({**summarize(selected, slip, args.commission_round_turn, "full", "all"), **concentration(selected), "candidate_id": candidate.candidate_id})
            for week, group in selected.groupby("forward_week", sort=True):
                rows.append({**summarize(group, slip, args.commission_round_turn, "week", str(week)), **concentration(group), "candidate_id": candidate.candidate_id})
            for day, group in selected.groupby("forward_date", sort=True):
                rows.append({**summarize(group, slip, args.commission_round_turn, "day", str(day)), **concentration(group), "candidate_id": candidate.candidate_id})
        summary = pd.DataFrame(rows)

    baseline = summary[(summary["scope"] == "full") & (summary["slippage_ticks_per_side"] == 0)].iloc[0]
    if reasons:
        verdict = "incomplete_data_lineage"
    elif baseline["trades"] < args.min_trades:
        verdict = "under_sampled_continue_monitoring"
        reasons.append(f"Only {int(baseline['trades'])} trades; minimum is {args.min_trades}.")
    elif baseline["weeks"] < args.min_weeks:
        verdict = "under_sampled_continue_monitoring"
        reasons.append(f"Only {int(baseline['weeks'])} weeks; minimum is {args.min_weeks}.")
    elif baseline["net_dollars"] <= 0 or baseline["profit_factor"] < 1.10 or baseline["max_drawdown_dollars"] > 2500 or baseline["net_without_largest"] <= 0 or (pd.notna(baseline["largest_winner_share"]) and baseline["largest_winner_share"] >= 0.50):
        verdict = "fail_demote_to_diagnostic_only"
    else:
        two_tick = summary[(summary["scope"] == "full") & (summary["slippage_ticks_per_side"] == 2)]
        if not two_tick.empty and float(two_tick.iloc[0]["profit_factor"]) < 1.05:
            verdict = "fail_demote_to_diagnostic_only"
            reasons.append("PF under 2 ticks per side slippage is below 1.05.")
        else:
            verdict = "pass_forward_validation"

    config = {
        "schema_version": 1,
        "generated_by": "scripts/run_donchian_forward_validation.py",
        "github_issue": "https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/11",
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
    write_source_lineage(out_dir / "source_lineage.md", input_manifest, verdict, reasons)
    write_verdict(out_dir / "VERDICT.md", summary, checks_df, verdict, reasons)
    print(out_dir / "VERDICT.md")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
