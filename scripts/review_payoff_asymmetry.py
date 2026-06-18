#!/usr/bin/env python3
"""Review whether vwap_delta_rejection winners reliably outweigh losers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_formula_regime_shift import PERIODS, assign_period, load_formula_context  # noqa: E402
from pattern_ml_research import max_drawdown  # noqa: E402


MIN_PAYOFF_RATIO = 1.30
MIN_PROFIT_FACTOR = 1.20
MIN_EDGE_MARGIN = 0.03
MIN_CONFIDENCE_TRADES = 20
MIN_CONFIDENCE_WINS = 5
MIN_CONFIDENCE_LOSSES = 5
SLIPPAGE_TICKS_PER_SIDE = [0, 1, 2, 4]
MNQ_ROUND_TRIP_DOLLARS_PER_TICK_PER_SIDE = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--research-dir",
        type=Path,
        default=Path("reports/pattern_ml_20260612"),
    )
    parser.add_argument(
        "--baseline-trades",
        type=Path,
        default=Path("reports/canonical_corrected_20260611/mnq_06_26_trades.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/pattern_ml_20260612/payoff_asymmetry"),
    )
    parser.add_argument("--bootstrap-repetitions", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260613)
    return parser.parse_args()


def payoff_metrics(values: pd.Series) -> dict:
    pnl = pd.Series(values, dtype=float).dropna()
    wins = pnl[pnl > 0]
    losses = -pnl[pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.sum())
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    win_rate = float(len(wins) / len(pnl)) if len(pnl) else 0.0
    breakeven_win_rate = 1.0 / (1.0 + payoff_ratio) if np.isfinite(payoff_ratio) else 0.0
    largest_winner = float(wins.max()) if len(wins) else 0.0
    gross_profit_without_largest = gross_profit - largest_winner
    profit_factor_without_largest = (
        gross_profit_without_largest / gross_loss if gross_loss > 0 else float("inf")
    )
    top_three_profit = float(wins.nlargest(3).sum()) if len(wins) else 0.0
    return {
        "trades": len(pnl),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "loss_to_win_size_ratio": avg_loss / avg_win if avg_win > 0 else float("inf"),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "expectancy": float(pnl.mean()) if len(pnl) else 0.0,
        "median_pnl": float(pnl.median()) if len(pnl) else 0.0,
        "breakeven_win_rate": breakeven_win_rate,
        "edge_margin": win_rate - breakeven_win_rate,
        "largest_winner": largest_winner,
        "largest_loser": float(losses.max()) if len(losses) else 0.0,
        "largest_winner_share": largest_winner / gross_profit if gross_profit > 0 else 0.0,
        "top_three_winner_share": top_three_profit / gross_profit if gross_profit > 0 else 0.0,
        "profit_factor_without_largest_winner": profit_factor_without_largest,
        "net_pnl": float(pnl.sum()),
        "max_drawdown": max_drawdown(pnl),
    }


def bootstrap_metrics(
    values: pd.Series,
    repetitions: int,
    seed: int,
) -> dict:
    pnl = pd.Series(values, dtype=float).dropna().to_numpy()
    if len(pnl) < 5:
        return {
            "payoff_ratio_ci_low": float("nan"),
            "payoff_ratio_ci_high": float("nan"),
            "profit_factor_ci_low": float("nan"),
            "profit_factor_ci_high": float("nan"),
            "expectancy_ci_low": float("nan"),
            "expectancy_ci_high": float("nan"),
            "probability_payoff_above_gate": float("nan"),
            "probability_profit_factor_above_gate": float("nan"),
            "probability_positive_expectancy": float("nan"),
        }
    rng = np.random.default_rng(seed)
    payoff = []
    profit_factor = []
    expectancy = []
    for _ in range(repetitions):
        sample = pnl[rng.integers(0, len(pnl), size=len(pnl))]
        metrics = payoff_metrics(pd.Series(sample))
        payoff.append(metrics["payoff_ratio"])
        profit_factor.append(metrics["profit_factor"])
        expectancy.append(metrics["expectancy"])
    payoff_values = np.asarray(payoff)
    pf_values = np.asarray(profit_factor)
    expectancy_values = np.asarray(expectancy)

    def empirical_quantile(values: np.ndarray, probability: float) -> float:
        ordered = np.sort(values)
        index = int(np.floor(probability * (len(ordered) - 1)))
        return float(ordered[index])

    return {
        "payoff_ratio_ci_low": empirical_quantile(payoff_values, 0.025),
        "payoff_ratio_ci_high": empirical_quantile(payoff_values, 0.975),
        "profit_factor_ci_low": empirical_quantile(pf_values, 0.025),
        "profit_factor_ci_high": empirical_quantile(pf_values, 0.975),
        "expectancy_ci_low": empirical_quantile(expectancy_values, 0.025),
        "expectancy_ci_high": empirical_quantile(expectancy_values, 0.975),
        "probability_payoff_above_gate": float((payoff_values >= MIN_PAYOFF_RATIO).mean()),
        "probability_profit_factor_above_gate": float((pf_values >= MIN_PROFIT_FACTOR).mean()),
        "probability_positive_expectancy": float((expectancy_values > 0).mean()),
    }


def summarize_group(
    group: pd.DataFrame,
    repetitions: int,
    seed: int,
) -> dict:
    metrics = payoff_metrics(group["net_pnl"])
    bootstrap = bootstrap_metrics(group["net_pnl"], repetitions, seed)
    metrics.update(bootstrap)
    metrics["passes_point_estimate_gate"] = bool(
        metrics["payoff_ratio"] >= MIN_PAYOFF_RATIO
        and metrics["profit_factor"] >= MIN_PROFIT_FACTOR
        and metrics["edge_margin"] >= MIN_EDGE_MARGIN
        and metrics["expectancy"] > 0
        and metrics["profit_factor_without_largest_winner"] >= 1.0
    )
    metrics["passes_confidence_gate"] = bool(
        metrics["trades"] >= MIN_CONFIDENCE_TRADES
        and metrics["wins"] >= MIN_CONFIDENCE_WINS
        and metrics["losses"] >= MIN_CONFIDENCE_LOSSES
        and metrics["payoff_ratio_ci_low"] >= 1.0
        and metrics["profit_factor_ci_low"] >= 1.0
        and metrics["expectancy_ci_low"] > 0
    )
    return metrics


def build_period_review(rows: pd.DataFrame, repetitions: int, seed: int) -> pd.DataFrame:
    records = []
    for index, (period, group) in enumerate(rows.groupby("period", sort=False)):
        records.append(
            {
                "period": period,
                **summarize_group(group, repetitions, seed + index),
            }
        )
    return pd.DataFrame(records)


def build_cohort_review(rows: pd.DataFrame, repetitions: int, seed: int) -> pd.DataFrame:
    development = rows[rows["period"].isin(["early_development", "late_development"])]
    low_vol, high_vol = development["rv_15m_atr"].quantile([0.33, 0.67]).tolist()
    rows = rows.copy()
    rows["volatility_regime"] = np.select(
        [rows["rv_15m_atr"] <= low_vol, rows["rv_15m_atr"] >= high_vol],
        ["low", "high"],
        default="mid",
    )
    rows["market_session"] = np.where(rows["session_bucket"] == "overnight", "overnight", "rth")
    rows["depth_provenance"] = np.where(rows["depth_live_ratio"] >= 0.5, "mostly_live", "mostly_replay")
    records = []
    group_number = 0
    for dimension in ["direction_label", "volatility_regime", "market_session", "depth_provenance"]:
        for (period, value), group in rows.groupby(["period", dimension], sort=True):
            if len(group) < 5:
                continue
            records.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "period": period,
                    **summarize_group(group, repetitions, seed + group_number),
                }
            )
            group_number += 1
    return pd.DataFrame(records)


def build_rolling_review(rows: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    ordered = rows.sort_values("decision_time").reset_index(drop=True)
    records = []
    for end in range(window, len(ordered) + 1):
        group = ordered.iloc[end - window : end]
        metrics = payoff_metrics(group["net_pnl"])
        records.append(
            {
                "window_start": group.iloc[0]["decision_time"],
                "window_end": group.iloc[-1]["decision_time"],
                "window_trades": window,
                "payoff_ratio": metrics["payoff_ratio"],
                "profit_factor": metrics["profit_factor"],
                "expectancy": metrics["expectancy"],
                "win_rate": metrics["win_rate"],
                "profit_factor_without_largest_winner": metrics[
                    "profit_factor_without_largest_winner"
                ],
            }
        )
    return pd.DataFrame(records)


def build_cost_sensitivity(rows: pd.DataFrame) -> pd.DataFrame:
    records = []
    for ticks_per_side in SLIPPAGE_TICKS_PER_SIDE:
        adjusted = rows.copy()
        adjusted["net_pnl"] = adjusted["net_pnl"] - (
            ticks_per_side * MNQ_ROUND_TRIP_DOLLARS_PER_TICK_PER_SIDE
        )
        for period, group in adjusted.groupby("period", sort=False):
            records.append(
                {
                    "period": period,
                    "slippage_ticks_per_side": ticks_per_side,
                    **payoff_metrics(group["net_pnl"]),
                }
            )
    return pd.DataFrame(records)


def format_money(value: float) -> str:
    return f"${value:+.2f}"


def write_report(
    periods: pd.DataFrame,
    cohorts: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    output: Path,
) -> None:
    lines = [
        "# Payoff-Asymmetry Review",
        "",
        "Primary objective: winners must outweigh losers by enough to create robust expectancy. "
        "A high win rate is neither required nor sufficient.",
        "",
        "## Frozen Metrics",
        "",
        "- Payoff ratio: average winner / average loser.",
        "- Profit factor: total winning dollars / total losing dollars.",
        "- Edge margin: observed win rate minus the break-even win rate implied by the payoff ratio.",
        f"- Point-estimate gate: payoff ratio >= {MIN_PAYOFF_RATIO:.2f}, profit factor >= "
        f"{MIN_PROFIT_FACTOR:.2f}, edge margin >= {MIN_EDGE_MARGIN:.0%}, positive expectancy, "
        "and profit factor >= 1.0 after removing the largest winner.",
        "- Confidence gate: at least 20 trades with at least five winners and five losers, plus 95% "
        "bootstrap lower bounds above break-even for payoff ratio, profit factor, and expectancy.",
        "- Period results below include commission but no added slippage, matching the existing formula baseline. "
        "The cost-sensitivity table applies additional MNQ slippage.",
        "",
        "## Period Results",
        "",
        "| Period | Trades | Win rate | Avg win | Avg loss | Payoff | Profit factor | Expectancy | PF without largest winner | Point gate | Confidence gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in periods.itertuples(index=False):
        lines.append(
            f"| `{row.period}` | {row.trades} | {row.win_rate:.1%} | {format_money(row.avg_win)} | "
            f"${row.avg_loss:.2f} | {row.payoff_ratio:.2f} | {row.profit_factor:.2f} | "
            f"{format_money(row.expectancy)} | {row.profit_factor_without_largest_winner:.2f} | "
            f"{'pass' if row.passes_point_estimate_gate else 'fail'} | "
            f"{'pass' if row.passes_confidence_gate else 'fail'} |"
        )
    lines.extend(
        [
            "",
            "## Confidence",
            "",
            "| Period | Payoff 95% CI | Profit factor 95% CI | Expectancy 95% CI | P(PF >= gate) | P(E > 0) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in periods.itertuples(index=False):
        lines.append(
            f"| `{row.period}` | {row.payoff_ratio_ci_low:.2f} to {row.payoff_ratio_ci_high:.2f} | "
            f"{row.profit_factor_ci_low:.2f} to {row.profit_factor_ci_high:.2f} | "
            f"{format_money(row.expectancy_ci_low)} to {format_money(row.expectancy_ci_high)} | "
            f"{row.probability_profit_factor_above_gate:.1%} | {row.probability_positive_expectancy:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Slippage Sensitivity",
            "",
            "| Period | Slippage ticks / side | Payoff | Profit factor | Expectancy | PF without largest winner | Net PnL |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in cost_sensitivity.itertuples(index=False):
        lines.append(
            f"| `{row.period}` | {row.slippage_ticks_per_side} | {row.payoff_ratio:.2f} | "
            f"{row.profit_factor:.2f} | {format_money(row.expectancy)} | "
            f"{row.profit_factor_without_largest_winner:.2f} | {format_money(row.net_pnl)} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
        ]
    )
    later = periods[periods["period"].isin(["validation", "final_test"])]
    development = periods[periods["period"].isin(["early_development", "late_development"])]
    if bool(later["passes_point_estimate_gate"].all()):
        lines.append(
            "Validation and final-test winners are materially larger than losers, so the candidate's recent "
            "profit is not merely a high-win-rate effect."
        )
    if not bool(development["passes_point_estimate_gate"].all()):
        lines.append(
            "However, payoff asymmetry was not stable through development. Late development had insufficient "
            "winner size and total gross profit to cover losses."
        )
    if not bool(periods["passes_confidence_gate"].any()):
        lines.append(
            "No period passes the strict confidence gate. The samples remain too small or too unstable to prove "
            "that the favorable payoff ratio is durable."
        )
    lines.extend(
        [
            "",
            "**Verdict: optimize the review around payoff asymmetry, but do not optimize the strategy on these "
            "historical blocks. The prospective gate must prove that winners remain larger than losers and that "
            "gross wins exceed gross losses after removing the largest winner.**",
            "",
            "Supporting files: `period_payoff.csv`, `cohort_payoff.csv`, `rolling_payoff.csv`, "
            "`cost_sensitivity.csv`, and `gate.json`.",
        ]
    )
    output.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = load_formula_context(args)
    rows["period"] = assign_period(rows["trading_day"].astype(str))
    rows = rows[rows["period"] != "excluded"].copy()
    periods = build_period_review(rows, args.bootstrap_repetitions, args.seed)
    cohorts = build_cohort_review(rows, min(args.bootstrap_repetitions, 2000), args.seed + 1000)
    rolling = build_rolling_review(rows)
    cost_sensitivity = build_cost_sensitivity(rows)
    periods.to_csv(args.out / "period_payoff.csv", index=False, float_format="%.8f")
    cohorts.to_csv(args.out / "cohort_payoff.csv", index=False, float_format="%.8f")
    rolling.to_csv(args.out / "rolling_payoff.csv", index=False, float_format="%.8f")
    cost_sensitivity.to_csv(args.out / "cost_sensitivity.csv", index=False, float_format="%.8f")
    gate = {
        "minimum_payoff_ratio": MIN_PAYOFF_RATIO,
        "minimum_profit_factor": MIN_PROFIT_FACTOR,
        "minimum_edge_margin": MIN_EDGE_MARGIN,
        "require_positive_expectancy": True,
        "minimum_profit_factor_without_largest_winner": 1.0,
        "confidence_gate": {
            "minimum_trades": MIN_CONFIDENCE_TRADES,
            "minimum_wins": MIN_CONFIDENCE_WINS,
            "minimum_losses": MIN_CONFIDENCE_LOSSES,
            "payoff_ratio_95pct_lower_bound": 1.0,
            "profit_factor_95pct_lower_bound": 1.0,
            "expectancy_95pct_lower_bound": 0.0,
        },
        "slippage_ticks_per_side_reviewed": SLIPPAGE_TICKS_PER_SIDE,
    }
    (args.out / "gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    write_report(periods, cohorts, cost_sensitivity, args.out / "VERDICT.md")
    print(f"wrote payoff-asymmetry review to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
