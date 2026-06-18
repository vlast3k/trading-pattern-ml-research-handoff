#!/usr/bin/env python3
"""Monitor frozen prospective vwap_delta_rejection results without retuning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pattern_ml_research import FORMULA_VARIANT, POINT_VALUE, TICK_SIZE, max_drawdown
from review_payoff_asymmetry import (
    MIN_EDGE_MARGIN,
    MIN_PAYOFF_RATIO,
    MIN_PROFIT_FACTOR,
    payoff_metrics,
)

EMBEDDED_ROUND_TURN_COST = 2.0
INTERIM_TRADES = 50
INTERIM_DAYS = 20
DECISION_TRADES = 200
DECISION_DAYS = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path("reports/canonical_corrected_20260611/mnq_06_26_trades.csv"),
    )
    parser.add_argument("--cutoff", default="2026-06-12")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/pattern_ml_20260612/prospective_monitor"),
    )
    parser.add_argument("--commission-round-turn", type=float, default=1.24)
    parser.add_argument("--slippage-ticks-per-side", type=float, default=1.0)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260613)
    return parser.parse_args()


def load_new_trades(
    path: Path,
    cutoff: str,
    commission: float,
    slippage_ticks_per_side: float,
) -> pd.DataFrame:
    rows = pd.read_csv(path)
    rows = rows[
        (rows["timeframe"] == 1)
        & (rows["variant"] == FORMULA_VARIANT)
        & (rows["trading_day"].astype(str) > cutoff)
    ].copy()
    rows["decision_time"] = pd.to_datetime(rows["signal_time"], utc=True)
    rows["entry_time"] = pd.to_datetime(rows["entry_time"], utc=True)
    rows["exit_time"] = pd.to_datetime(rows["exit_time"], utc=True)
    # Analyzer `r` already includes its configured $2 round-turn cost.
    rows["gross_pnl"] = (
        rows["r"].astype(float) * rows["risk_points"].astype(float) * POINT_VALUE
        + EMBEDDED_ROUND_TURN_COST
    )
    fixed_cost = commission + 2.0 * slippage_ticks_per_side * TICK_SIZE * POINT_VALUE
    rows["net_pnl"] = rows["gross_pnl"] - fixed_cost
    rows["profitable"] = rows["net_pnl"] > 0
    return select_nonoverlapping(rows.sort_values("decision_time"))


def select_nonoverlapping(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    selected = []
    next_free: pd.Timestamp | None = None
    for row in rows.sort_values(["decision_time", "exit_time"]).itertuples(index=False):
        if next_free is not None and row.decision_time < next_free:
            continue
        selected.append(row)
        next_free = row.exit_time
    return pd.DataFrame(selected, columns=rows.columns)


def trading_day_bootstrap(rows: pd.DataFrame, repetitions: int, seed: int) -> dict:
    if rows.empty:
        return {
            "bootstrap_repetitions": repetitions,
            "expectancy_ci_low": 0.0,
            "expectancy_ci_high": 0.0,
            "profit_factor_ci_low": 0.0,
            "profit_factor_ci_high": 0.0,
            "probability_positive_expectancy": 0.0,
            "probability_profit_factor_above_one": 0.0,
        }
    groups = [group["net_pnl"].to_numpy() for _, group in rows.groupby("trading_day")]
    rng = np.random.default_rng(seed)
    expectancy = []
    profit_factor = []
    for _ in range(repetitions):
        sample = np.concatenate([groups[index] for index in rng.integers(0, len(groups), len(groups))])
        wins = sample[sample > 0].sum()
        losses = -sample[sample < 0].sum()
        expectancy.append(float(sample.mean()))
        profit_factor.append(float(wins / losses) if losses > 0 else float("inf"))
    exp = np.asarray(expectancy)
    pf = np.asarray(profit_factor)
    return {
        "bootstrap_repetitions": repetitions,
        "expectancy_ci_low": float(np.quantile(exp, 0.025)),
        "expectancy_ci_high": float(np.quantile(exp, 0.975)),
        "profit_factor_ci_low": float(np.quantile(pf, 0.025)),
        "profit_factor_ci_high": float(np.quantile(pf, 0.975)),
        "probability_positive_expectancy": float((exp > 0).mean()),
        "probability_profit_factor_above_one": float((pf > 1).mean()),
    }


def summarize(rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {
            "trades": 0,
            "substantial_days": 0,
            "long_trades": 0,
            "short_trades": 0,
            "contract_periods": 0,
            "net_pnl": 0.0,
            "profitable_rate": 0.0,
            "max_drawdown": 0.0,
            "leave_best_day_out_pnl": 0.0,
            "first_half_pnl": 0.0,
            "second_half_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "payoff_ratio": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "breakeven_win_rate": 0.0,
            "edge_margin": 0.0,
            "profit_factor_without_largest_winner": 0.0,
            "passes_payoff_gate": False,
        }
    by_day = rows.groupby("trading_day")["net_pnl"].sum().sort_values(ascending=False)
    midpoint = len(rows) // 2
    payoff = payoff_metrics(rows["net_pnl"])
    return {
        "trades": len(rows),
        "substantial_days": int(rows["trading_day"].nunique()),
        "long_trades": int((rows["direction"] == "long").sum()),
        "short_trades": int((rows["direction"] == "short").sum()),
        "contract_periods": int(rows["instrument"].nunique()) if "instrument" in rows else 0,
        "net_pnl": float(rows["net_pnl"].sum()),
        "profitable_rate": float(rows["profitable"].mean()),
        "max_drawdown": max_drawdown(rows["net_pnl"]),
        "leave_best_day_out_pnl": float(rows["net_pnl"].sum() - by_day.iloc[0]),
        "first_half_pnl": float(rows.iloc[:midpoint]["net_pnl"].sum()),
        "second_half_pnl": float(rows.iloc[midpoint:]["net_pnl"].sum()),
        "avg_win": payoff["avg_win"],
        "avg_loss": payoff["avg_loss"],
        "payoff_ratio": payoff["payoff_ratio"],
        "profit_factor": payoff["profit_factor"],
        "expectancy": payoff["expectancy"],
        "breakeven_win_rate": payoff["breakeven_win_rate"],
        "edge_margin": payoff["edge_margin"],
        "profit_factor_without_largest_winner": payoff["profit_factor_without_largest_winner"],
        "passes_payoff_gate": bool(
            payoff["payoff_ratio"] >= MIN_PAYOFF_RATIO
            and payoff["profit_factor"] >= MIN_PROFIT_FACTOR
            and payoff["edge_margin"] >= MIN_EDGE_MARGIN
            and payoff["expectancy"] > 0
            and payoff["profit_factor_without_largest_winner"] >= 1.0
        ),
    }


def write_report(
    summary: dict,
    bootstrap: dict,
    cutoff: str,
    fixed_cost: float,
    slippage_ticks_per_side: float,
    output: Path,
) -> None:
    interim_complete = summary["trades"] >= INTERIM_TRADES and summary["substantial_days"] >= INTERIM_DAYS
    decision_count_complete = (
        summary["trades"] >= DECISION_TRADES
        and summary["substantial_days"] >= DECISION_DAYS
        and summary["contract_periods"] >= 2
    )
    confidence_complete = (
        bootstrap["expectancy_ci_low"] > 0
        and bootstrap["profit_factor_ci_low"] > 1
    )
    lines = [
        "# Frozen Prospective Monitor",
        "",
        f"- Frozen cutoff: after `{cutoff}`.",
        "- Formula: exact MNQ 1-minute `vwap_delta_rejection`, all signals, no filters.",
        f"- Per-trade cost: `${fixed_cost:.2f}` including `{slippage_ticks_per_side:g}` slippage tick(s) per side.",
        f"- Interim evidence count complete: `{'yes' if interim_complete else 'no'}`.",
        f"- Decision-grade count complete: `{'yes' if decision_count_complete else 'no'}`.",
        f"- Trading-day bootstrap confidence complete: `{'yes' if confidence_complete else 'no'}`.",
        f"- Contract/roll periods observed: `{summary['contract_periods']}`.",
        f"- Payoff gate currently passes: `{'yes' if summary['passes_payoff_gate'] else 'no'}`.",
        "",
        "| Trades | Days | Long / Short | Profitable | Net PnL | Max DD | Leave best day out | First / second half |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {summary['trades']} | {summary['substantial_days']} | "
        f"{summary['long_trades']} / {summary['short_trades']} | {summary['profitable_rate']:.1%} | "
        f"${summary['net_pnl']:+.2f} | ${summary['max_drawdown']:.2f} | "
        f"${summary['leave_best_day_out_pnl']:+.2f} | "
        f"${summary['first_half_pnl']:+.2f} / ${summary['second_half_pnl']:+.2f} |",
        "",
        "| Avg winner | Avg loser | Winner/loss size | Profit factor | Expectancy | Break-even win rate | Edge margin | PF without largest winner |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| ${summary['avg_win']:.2f} | ${summary['avg_loss']:.2f} | "
        f"{summary['payoff_ratio']:.2f}x | {summary['profit_factor']:.2f} | "
        f"${summary['expectancy']:+.2f} | {summary['breakeven_win_rate']:.1%} | "
        f"{summary['edge_margin']:+.1%} | {summary['profit_factor_without_largest_winner']:.2f} |",
        "",
        "## Trading-Day Bootstrap",
        "",
        f"- Repetitions: `{bootstrap['bootstrap_repetitions']}`.",
        f"- Expectancy 95% interval: `${bootstrap['expectancy_ci_low']:+.2f}` to "
        f"`${bootstrap['expectancy_ci_high']:+.2f}`.",
        f"- Profit-factor 95% interval: `{bootstrap['profit_factor_ci_low']:.2f}` to "
        f"`{bootstrap['profit_factor_ci_high']:.2f}`.",
        f"- Probability of positive expectancy: `{bootstrap['probability_positive_expectancy']:.1%}`.",
        "",
    ]
    if not interim_complete:
        lines.append("**Status: collecting evidence. Do not promote or retune.**")
    elif not decision_count_complete or not confidence_complete:
        lines.append("**Status: interim checkpoint reached, but decision-grade gate has not passed. Do not promote or retune.**")
    else:
        lines.append("**Status: statistical gates reached. Complete contract-roll and execution audit before any decision.**")
    output.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = load_new_trades(
        args.trades,
        args.cutoff,
        args.commission_round_turn,
        args.slippage_ticks_per_side,
    )
    summary = summarize(rows)
    bootstrap = trading_day_bootstrap(rows, args.bootstrap_repetitions, args.seed)
    fixed_cost = args.commission_round_turn + (
        2.0 * args.slippage_ticks_per_side * TICK_SIZE * POINT_VALUE
    )
    rows.to_csv(args.out / "prospective_trades.csv", index=False, float_format="%.8f")
    (args.out / "summary.json").write_text(
        json.dumps(
            {
                "cutoff": args.cutoff,
                "commission_round_turn": args.commission_round_turn,
                "slippage_ticks_per_side": args.slippage_ticks_per_side,
                "fixed_cost": fixed_cost,
                **summary,
                **bootstrap,
            },
            indent=2,
        )
        + "\n"
    )
    write_report(
        summary,
        bootstrap,
        args.cutoff,
        fixed_cost,
        args.slippage_ticks_per_side,
        args.out / "STATUS.md",
    )
    print(f"wrote prospective monitor to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
