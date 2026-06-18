#!/usr/bin/env python3
"""Summarize a primary-only analyzer replication with one-position execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path("reports/mnq_2025q1_primary_replication/mnq_databento_trades.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/mnq_2025q1_primary_replication"),
    )
    parser.add_argument("--bootstrap-repetitions", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260613)
    return parser.parse_args()


def select_nonoverlap(rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows.sort_values("entry_time")
    selected = []
    active_until = None
    for row in rows.itertuples(index=False):
        if active_until is None or row.entry_time >= active_until:
            selected.append(row._asdict())
            active_until = row.exit_time
    return pd.DataFrame(selected)


def metrics(rows: pd.DataFrame) -> dict[str, float]:
    pnl = rows["pnl"]
    wins = pnl[pnl > 0]
    losses = -pnl[pnl < 0]
    equity = pnl.cumsum()
    daily = rows.groupby("trading_day")["pnl"].sum()
    return {
        "trades": len(rows),
        "days": daily.size,
        "long_trades": int(rows["direction"].eq("long").sum()),
        "short_trades": int(rows["direction"].eq("short").sum()),
        "win_rate": float((pnl > 0).mean()),
        "net_pnl": float(pnl.sum()),
        "profit_factor": float(wins.sum() / losses.sum()) if losses.sum() else float("inf"),
        "payoff_ratio": float(wins.mean() / losses.mean()) if len(wins) and len(losses) else 0.0,
        "expectancy": float(pnl.mean()),
        "max_drawdown": float((equity.cummax() - equity).max()),
        "worst_day": float(daily.min()),
        "leave_best_day_out_pnl": float(pnl.sum() - daily.max()),
        "profit_factor_without_largest_winner": float(
            (wins.sum() - wins.max()) / losses.sum()
        ) if len(wins) and losses.sum() else 0.0,
        "first_half_pnl": float(pnl.iloc[: len(rows) // 2].sum()),
        "second_half_pnl": float(pnl.iloc[len(rows) // 2 :].sum()),
    }


def bootstrap(rows: pd.DataFrame, repetitions: int, seed: int) -> dict[str, float]:
    daily = [group["pnl"].to_numpy() for _, group in rows.groupby("trading_day")]
    rng = np.random.default_rng(seed)
    exp = []
    pf = []
    for _ in range(repetitions):
        sample = np.concatenate([daily[i] for i in rng.integers(0, len(daily), len(daily))])
        exp.append(float(sample.mean()))
        wins = sample[sample > 0].sum()
        losses = -sample[sample < 0].sum()
        pf.append(float(wins / losses) if losses else float("inf"))
    return {
        "repetitions": repetitions,
        "expectancy_95pct_low": float(np.quantile(exp, 0.025)),
        "expectancy_95pct_high": float(np.quantile(exp, 0.975)),
        "profit_factor_95pct_low": float(np.quantile(pf, 0.025)),
        "profit_factor_95pct_high": float(np.quantile(pf, 0.975)),
        "probability_positive_expectancy": float(np.mean(np.asarray(exp) > 0)),
    }


def main() -> None:
    args = parse_args()
    rows = pd.read_csv(args.trades)
    rows["entry_time"] = pd.to_datetime(rows["entry_time"], utc=True)
    rows["exit_time"] = pd.to_datetime(rows["exit_time"], utc=True)
    rows["pnl"] = rows["r"] * rows["risk_points"] * 2.0
    rows = select_nonoverlap(rows)
    summary = metrics(rows)
    boot = bootstrap(rows, args.bootstrap_repetitions, args.seed)
    payload = {"summary": summary, "trading_day_bootstrap": boot}
    args.out.mkdir(parents=True, exist_ok=True)
    rows.to_csv(args.out / "primary_nonoverlapping_trades.csv", index=False, float_format="%.10f")
    (args.out / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="ascii")
    passes = (
        summary["profit_factor"] >= 1.20
        and summary["payoff_ratio"] >= 1.30
        and summary["leave_best_day_out_pnl"] > 0
        and summary["profit_factor_without_largest_winner"] >= 1.0
        and boot["expectancy_95pct_low"] > 0
        and boot["profit_factor_95pct_low"] > 1.0
    )
    verdict = [
        "# 2025 Q1 Frozen Primary Replication",
        "",
        "**Verdict: " + ("passes the registered statistical gates." if passes else "does not pass the registered statistical gates.") + "**",
        "",
        "This is an independent historical replication of only the frozen MNQ 1-minute "
        "`vwap_delta_rejection` candidate. It uses the dominant outright MNQ contract per "
        "UTC day, one open position at a time, and the `$2.24` modeled round-turn cost.",
        "",
        f"- Trades / days: `{summary['trades']}` / `{summary['days']}`.",
        f"- Long / short: `{summary['long_trades']}` / `{summary['short_trades']}`.",
        f"- Net PnL: `${summary['net_pnl']:+,.2f}`; expectancy `${summary['expectancy']:+,.2f}`.",
        f"- Profit factor: `{summary['profit_factor']:.2f}`; payoff ratio `{summary['payoff_ratio']:.2f}`.",
        f"- Maximum drawdown: `${summary['max_drawdown']:,.2f}`; worst day `${summary['worst_day']:,.2f}`.",
        f"- Leave-best-day-out PnL: `${summary['leave_best_day_out_pnl']:+,.2f}`.",
        f"- Profit factor without largest winner: `{summary['profit_factor_without_largest_winner']:.2f}`.",
        f"- First / second half PnL: `${summary['first_half_pnl']:+,.2f}` / `${summary['second_half_pnl']:+,.2f}`.",
        f"- Trading-day bootstrap expectancy 95% interval: "
        f"`${boot['expectancy_95pct_low']:+,.2f}` to `${boot['expectancy_95pct_high']:+,.2f}`.",
        f"- Trading-day bootstrap PF 95% interval: "
        f"`{boot['profit_factor_95pct_low']:.2f}` to `{boot['profit_factor_95pct_high']:.2f}`.",
        "",
        "This result must remain separate from prospective evidence. Alternative-strategy "
        "outcomes have not been generated in this primary-only analyzer run.",
    ]
    (args.out / "VERDICT.md").write_text("\n".join(verdict) + "\n", encoding="ascii")
    print(f"Wrote primary replication verdict to {args.out}")


if __name__ == "__main__":
    main()
