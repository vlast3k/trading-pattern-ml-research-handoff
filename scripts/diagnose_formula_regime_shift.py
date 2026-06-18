#!/usr/bin/env python3
"""Diagnose the vwap_delta_rejection regime shift without optimizing on final data."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pattern_ml_research import (  # noqa: E402
    MODEL_FEATURES,
    ResearchConfig,
    build_formula_filter_rows,
    load_formula_baseline,
    max_drawdown,
)


PERIODS = [
    ("early_development", "2026-04-01", "2026-04-17"),
    ("late_development", "2026-04-18", "2026-05-15"),
    ("validation", "2026-05-18", "2026-05-22"),
    ("final_test", "2026-05-25", "2026-06-05"),
]

DIAGNOSTIC_FEATURES = [
    "risk_points",
    "atr_14",
    "rv_15m_atr",
    "range_1m_atr",
    "signed_ret_1m",
    "signed_ret_5m",
    "signed_ret_15m",
    "signed_ret_60m",
    "signed_dist_vwap_atr",
    "volume_ratio_20",
    "trades_ratio_20",
    "signed_delta_pct",
    "signed_delta_ratio_20",
    "spread_atr",
    "quote_ratio_20",
    "signed_depth_imbalance",
    "signed_depth_imbalance_change",
    "signed_depth_imbalance_persist_10",
    "depth_ratio_20",
    "signed_book_slope",
    "signed_nq_ret_1m",
    "signed_nq_ret_5m",
    "signed_mnq_nq_div_1m",
    "trade_live_ratio",
    "quote_live_ratio",
    "depth_live_ratio",
    "quality_ratio_60",
]


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
        default=Path("reports/pattern_ml_20260612/regime_shift"),
    )
    return parser.parse_args()


def assign_period(days: pd.Series) -> pd.Series:
    conditions = []
    labels = []
    for name, start, end in PERIODS:
        conditions.append((days >= start) & (days <= end))
        labels.append(name)
    return pd.Series(np.select(conditions, labels, default="excluded"), index=days.index)


def load_formula_context(args: argparse.Namespace) -> pd.DataFrame:
    minute = pd.read_csv(args.research_dir / "minute_features.csv.gz", parse_dates=["decision_time"])
    minute["decision_time"] = pd.to_datetime(minute["decision_time"], utc=True)
    config = ResearchConfig(
        Path("data/canonical_orderflow_1s"),
        args.baseline_trades,
        args.research_dir,
    )
    formula = load_formula_baseline(args.baseline_trades, config)
    rows = build_formula_filter_rows(formula, minute)
    extra = minute[
        [
            "decision_time",
            "atr_14",
            "trade_live_ratio",
            "quote_live_ratio",
            "depth_live_ratio",
            "quality_ratio_60",
        ]
    ].drop_duplicates("decision_time")
    rows = rows.drop(
        columns=[
            column
            for column in extra.columns
            if column != "decision_time" and column in rows.columns
        ]
    ).merge(extra, on="decision_time", how="left", validate="one_to_one")
    rows["period"] = assign_period(rows["trading_day"].astype(str))
    rows = rows[rows["period"] != "excluded"].copy()
    rows["direction_label"] = np.where(rows["direction"] > 0, "long", "short")
    rows["profitable"] = rows["net_pnl"] > 0
    rows["decision_time"] = pd.to_datetime(rows["decision_time"], utc=True)
    return rows.sort_values("decision_time").reset_index(drop=True)


def summary_record(group: pd.DataFrame) -> dict:
    by_day = group.groupby("trading_day")["net_pnl"].sum().sort_values(ascending=False)
    total = float(group["net_pnl"].sum())
    return {
        "trades": len(group),
        "profitable_rate": float(group["profitable"].mean()) if len(group) else 0.0,
        "net_pnl": total,
        "avg_net_pnl": float(group["net_pnl"].mean()) if len(group) else 0.0,
        "median_net_pnl": float(group["net_pnl"].median()) if len(group) else 0.0,
        "max_drawdown": max_drawdown(group.sort_values("decision_time")["net_pnl"]),
        "positive_days": int((by_day > 0).sum()),
        "negative_days": int((by_day < 0).sum()),
        "best_day": str(by_day.index[0]) if len(by_day) else "",
        "best_day_pnl": float(by_day.iloc[0]) if len(by_day) else 0.0,
        "best_day_share": float(by_day.iloc[0] / total) if total > 0 and len(by_day) else 0.0,
        "leave_best_day_out_pnl": total - float(by_day.iloc[0]) if len(by_day) else total,
    }


def build_period_summary(rows: pd.DataFrame) -> pd.DataFrame:
    records = []
    for period, group in rows.groupby("period", sort=False):
        records.append({"period": period, **summary_record(group)})
    return pd.DataFrame(records)


def population_stability_index(reference: pd.Series, comparison: pd.Series) -> float:
    reference = reference.dropna().astype(float)
    comparison = comparison.dropna().astype(float)
    if len(reference) < 10 or len(comparison) < 5:
        return float("nan")
    edges = np.unique(reference.quantile(np.linspace(0.0, 1.0, 11)).to_numpy())
    if len(edges) < 3:
        categories = sorted(set(reference.unique()).union(comparison.unique()))
        ref_pct = np.asarray([(reference == value).mean() for value in categories], dtype=float)
        cmp_pct = np.asarray([(comparison == value).mean() for value in categories], dtype=float)
        ref_pct = np.maximum(ref_pct, 1e-6)
        cmp_pct = np.maximum(cmp_pct, 1e-6)
        return float(np.sum((cmp_pct - ref_pct) * np.log(cmp_pct / ref_pct)))
    edges[0] = -np.inf
    edges[-1] = np.inf
    ref_counts = pd.cut(reference, edges, include_lowest=True).value_counts(sort=False)
    cmp_counts = pd.cut(comparison, edges, include_lowest=True).value_counts(sort=False)
    ref_pct = np.maximum(ref_counts.to_numpy(dtype=float) / len(reference), 1e-6)
    cmp_pct = np.maximum(cmp_counts.to_numpy(dtype=float) / len(comparison), 1e-6)
    return float(np.sum((cmp_pct - ref_pct) * np.log(cmp_pct / ref_pct)))


def build_feature_drift(rows: pd.DataFrame) -> pd.DataFrame:
    development = rows[rows["period"].isin(["early_development", "late_development"])]
    records = []
    for comparison_name in ["validation", "final_test"]:
        comparison = rows[rows["period"] == comparison_name]
        for feature in DIAGNOSTIC_FEATURES:
            reference_values = development[feature].dropna().astype(float)
            comparison_values = comparison[feature].dropna().astype(float)
            pooled_std = math.sqrt(
                0.5
                * (
                    float(reference_values.var(ddof=1))
                    + float(comparison_values.var(ddof=1))
                )
            )
            standardized_difference = (
                (float(comparison_values.mean()) - float(reference_values.mean())) / pooled_std
                if pooled_std > 1e-12
                else 0.0
            )
            ks = ks_2samp(reference_values, comparison_values)
            records.append(
                {
                    "comparison": comparison_name,
                    "feature": feature,
                    "development_median": float(reference_values.median()),
                    "comparison_median": float(comparison_values.median()),
                    "standardized_mean_difference": standardized_difference,
                    "ks_statistic": float(ks.statistic),
                    "ks_pvalue": float(ks.pvalue),
                    "psi": population_stability_index(reference_values, comparison_values),
                }
            )
    return pd.DataFrame(records)


def build_outcome_association(rows: pd.DataFrame) -> pd.DataFrame:
    records = []
    for period, group in rows.groupby("period", sort=False):
        for feature in DIAGNOSTIC_FEATURES:
            usable = group[[feature, "net_pnl", "profitable"]].dropna()
            if usable[feature].nunique() < 2:
                correlation = 0.0
                pvalue = 1.0
            else:
                correlation, pvalue = spearmanr(usable[feature], usable["net_pnl"])
            records.append(
                {
                    "period": period,
                    "feature": feature,
                    "spearman_net_pnl": float(correlation),
                    "spearman_pvalue": float(pvalue),
                    "profitable_median": float(usable.loc[usable["profitable"], feature].median()),
                    "unprofitable_median": float(usable.loc[~usable["profitable"], feature].median()),
                }
            )
    return pd.DataFrame(records)


def build_cohort_stability(rows: pd.DataFrame) -> pd.DataFrame:
    development = rows[rows["period"].isin(["early_development", "late_development"])]
    low_vol, high_vol = development["rv_15m_atr"].quantile([0.33, 0.67]).tolist()
    volume_high = float(development["volume_ratio_20"].median())
    delta_high = float(development["signed_delta_pct"].median())
    rows = rows.copy()
    rows["volatility_regime"] = np.select(
        [rows["rv_15m_atr"] <= low_vol, rows["rv_15m_atr"] >= high_vol],
        ["low", "high"],
        default="mid",
    )
    rows["market_session"] = np.where(rows["session_bucket"] == "overnight", "overnight", "rth")
    rows["depth_provenance"] = np.where(rows["depth_live_ratio"] >= 0.5, "mostly_live", "mostly_replay")
    rows["volume_state"] = np.where(rows["volume_ratio_20"] >= volume_high, "higher_volume", "lower_volume")
    rows["signed_delta_state"] = np.where(rows["signed_delta_pct"] >= delta_high, "higher_signed_delta", "lower_signed_delta")
    records = []
    for dimension in [
        "direction_label",
        "volatility_regime",
        "market_session",
        "depth_provenance",
        "volume_state",
        "signed_delta_state",
    ]:
        for (period, value), group in rows.groupby(["period", dimension], sort=True):
            records.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "period": period,
                    **summary_record(group),
                }
            )
    return pd.DataFrame(records)


def build_rule_audit(rows: pd.DataFrame) -> pd.DataFrame:
    development = rows[rows["period"].isin(["early_development", "late_development"])]
    low_vol, high_vol = development["rv_15m_atr"].quantile([0.33, 0.67]).tolist()
    volume_high = float(development["volume_ratio_20"].median())
    delta_high = float(development["signed_delta_pct"].median())
    rules = {
        "all": lambda frame: np.ones(len(frame), dtype=bool),
        "long_only": lambda frame: frame["direction"] > 0,
        "short_only": lambda frame: frame["direction"] < 0,
        "overnight_only": lambda frame: frame["session_bucket"] == "overnight",
        "rth_only": lambda frame: frame["session_bucket"] != "overnight",
        "low_volatility": lambda frame: frame["rv_15m_atr"] <= low_vol,
        "mid_volatility": lambda frame: (frame["rv_15m_atr"] > low_vol)
        & (frame["rv_15m_atr"] < high_vol),
        "high_volatility": lambda frame: frame["rv_15m_atr"] >= high_vol,
        "long_high_volatility": lambda frame: (frame["direction"] > 0)
        & (frame["rv_15m_atr"] >= high_vol),
        "mostly_live_depth": lambda frame: frame["depth_live_ratio"] >= 0.5,
        "mostly_replay_depth": lambda frame: frame["depth_live_ratio"] < 0.5,
        "higher_volume": lambda frame: frame["volume_ratio_20"] >= volume_high,
        "higher_signed_delta": lambda frame: frame["signed_delta_pct"] >= delta_high,
    }
    records = []
    for rule_name, predicate in rules.items():
        per_period = {}
        for period, _, _ in PERIODS:
            selected = rows[(rows["period"] == period) & predicate(rows)]
            per_period[period] = selected
            record = {
                "rule": rule_name,
                "period": period,
                **summary_record(selected),
            }
            records.append(record)
        eligible = (
            len(per_period["early_development"]) >= 5
            and len(per_period["late_development"]) >= 5
            and float(per_period["early_development"]["net_pnl"].sum()) > 0
            and float(per_period["late_development"]["net_pnl"].sum()) > 0
            and summary_record(per_period["early_development"])["leave_best_day_out_pnl"] > 0
            and summary_record(per_period["late_development"])["leave_best_day_out_pnl"] > 0
        )
        for record in records:
            if record["rule"] == rule_name:
                record["chronologically_eligible"] = eligible
    return pd.DataFrame(records)


def build_change_point_audit(rows: pd.DataFrame, seed: int = 20260612) -> dict:
    ordered = rows.sort_values("decision_time").reset_index(drop=True)
    values = ordered["net_pnl"].to_numpy(dtype=float)
    best = None
    for split in range(30, len(values) - 30):
        before = values[:split]
        after = values[split:]
        difference = float(after.mean() - before.mean())
        score = abs(difference)
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "split_index": split,
                "split_time": ordered.iloc[split]["decision_time"].isoformat(),
                "split_trading_day": ordered.iloc[split]["trading_day"],
                "before_trades": len(before),
                "after_trades": len(after),
                "before_net_pnl": float(before.sum()),
                "after_net_pnl": float(after.sum()),
                "before_avg_pnl": float(before.mean()),
                "after_avg_pnl": float(after.mean()),
                "average_pnl_difference": difference,
            }
    rng = np.random.default_rng(seed)
    exceedances = 0
    for _ in range(2000):
        shuffled = rng.permutation(values)
        max_score = 0.0
        for split in range(30, len(values) - 30):
            max_score = max(max_score, abs(float(shuffled[split:].mean() - shuffled[:split].mean())))
        exceedances += int(max_score >= best["score"])
    best["permutation_pvalue_multiple_split_adjusted"] = (exceedances + 1) / 2001.0
    best["post_hoc_warning"] = (
        "The split was selected after viewing all outcomes and is diagnostic only."
    )
    return best


def format_money(value: float) -> str:
    return f"${value:+.2f}"


def write_report(
    rows: pd.DataFrame,
    summary: pd.DataFrame,
    drift: pd.DataFrame,
    cohorts: pd.DataFrame,
    rules: pd.DataFrame,
    change_point: dict,
    output_path: Path,
) -> None:
    lines = [
        "# VWAP Delta Rejection Regime-Shift Diagnosis",
        "",
        "This is a diagnostic audit, not a strategy-selection pass. All thresholds and predefined rules "
        "use development data only; the retrospective change point is explicitly marked post-hoc.",
        "",
        "## Period Results",
        "",
        "| Period | Trades | Profitable | Net PnL | Avg/trade | Max DD | Days + / - | Leave best day out |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| `{row.period}` | {row.trades} | {row.profitable_rate:.1%} | {format_money(row.net_pnl)} | "
            f"{format_money(row.avg_net_pnl)} | ${row.max_drawdown:.2f} | "
            f"{row.positive_days} / {row.negative_days} | {format_money(row.leave_best_day_out_pnl)} |"
        )
    lines.extend(
        [
            "",
            "## What Changed",
            "",
            "- The profitable phase begins around the second half of May and is primarily a long/high-volatility phenomenon.",
            "- A major replay-to-live provenance shift also occurred. It is a serious confounder, although later replay-only trades were profitable too, so it does not fully explain the result.",
            "- The final block is profitable without its best day, but May 28 and May 29 still contribute a large share.",
            "",
            "### Largest Feature Drifts",
            "",
            "| Comparison | Feature | Dev median | Later median | Std mean diff | PSI | KS statistic |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    top_drift = drift.assign(abs_smd=drift["standardized_mean_difference"].abs()).sort_values(
        ["comparison", "abs_smd"], ascending=[True, False]
    )
    for row in top_drift.groupby("comparison", sort=False).head(8).itertuples(index=False):
        lines.append(
            f"| `{row.comparison}` | `{row.feature}` | {row.development_median:.4f} | "
            f"{row.comparison_median:.4f} | {row.standardized_mean_difference:+.3f} | "
            f"{row.psi:.3f} | {row.ks_statistic:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Predefined Rule Audit",
            "",
            "A rule is chronologically eligible only if it has at least five trades, positive net PnL, and "
            "positive PnL after removing its best day in both early and late development. Validation/final "
            "results never make a rule eligible.",
            "",
            "| Rule | Eligible before validation? | Early dev | Late dev | Validation | Final test |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    pivot = rules.pivot(index="rule", columns="period", values="net_pnl")
    eligibility = rules.groupby("rule")["chronologically_eligible"].first()
    for rule in pivot.index:
        lines.append(
            f"| `{rule}` | {'yes' if eligibility[rule] else 'no'} | "
            f"{format_money(pivot.loc[rule, 'early_development'])} | "
            f"{format_money(pivot.loc[rule, 'late_development'])} | "
            f"{format_money(pivot.loc[rule, 'validation'])} | "
            f"{format_money(pivot.loc[rule, 'final_test'])} |"
        )
    lines.extend(
        [
            "",
            "## Retrospective Change Point",
            "",
            f"- Best post-hoc split: `{change_point['split_time']}` / trading day `{change_point['split_trading_day']}`.",
            f"- Before: {change_point['before_trades']} trades, {format_money(change_point['before_net_pnl'])}, "
            f"{format_money(change_point['before_avg_pnl'])}/trade.",
            f"- After: {change_point['after_trades']} trades, {format_money(change_point['after_net_pnl'])}, "
            f"{format_money(change_point['after_avg_pnl'])}/trade.",
            f"- Multiple-split-adjusted permutation p-value: {change_point['permutation_pvalue_multiple_split_adjusted']:.4f}.",
            "- This split was discovered using all outcomes and cannot be used as a trading rule.",
            "",
            "## Verdict",
            "",
        ]
    )
    eligible_rules = eligibility[eligibility].index.tolist()
    if eligible_rules:
        lines.append(
            "Some predefined rules were positive in both development halves, but they still require validation/final "
            "stability review before becoming candidates: " + ", ".join(f"`{rule}`" for rule in eligible_rules) + "."
        )
    else:
        lines.append(
            "**No tested regime rule was knowable and profitable across both development halves.** "
            "The later long/high-volatility strength is a real observed shift, but using it now as a filter would be post-hoc."
        )
    lines.extend(
        [
            "",
            "The correct next gate is prospective data after June 12, 2026, when this diagnosis and gate were "
            "frozen. Freeze the formula and diagnostics; "
            "do not tune a long/high-volatility filter on the validation/final blocks.",
            "",
            "Supporting files: `period_summary.csv`, `feature_drift.csv`, `outcome_association.csv`, "
            "`cohort_stability.csv`, `predefined_rule_audit.csv`, and `change_point_audit.json`.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = load_formula_context(args)
    rows.to_csv(args.out / "formula_context.csv.gz", index=False, compression="gzip", float_format="%.8f")
    summary = build_period_summary(rows)
    drift = build_feature_drift(rows)
    outcome = build_outcome_association(rows)
    cohorts = build_cohort_stability(rows)
    rules = build_rule_audit(rows)
    change_point = build_change_point_audit(rows)
    summary.to_csv(args.out / "period_summary.csv", index=False, float_format="%.8f")
    drift.to_csv(args.out / "feature_drift.csv", index=False, float_format="%.8f")
    outcome.to_csv(args.out / "outcome_association.csv", index=False, float_format="%.8f")
    cohorts.to_csv(args.out / "cohort_stability.csv", index=False, float_format="%.8f")
    rules.to_csv(args.out / "predefined_rule_audit.csv", index=False, float_format="%.8f")
    (args.out / "change_point_audit.json").write_text(json.dumps(change_point, indent=2) + "\n")
    write_report(rows, summary, drift, cohorts, rules, change_point, args.out / "VERDICT.md")
    print(f"wrote regime-shift diagnosis to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
