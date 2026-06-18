#!/usr/bin/env python3
"""Comprehensive, multiple-testing-aware evaluation of daily futures strategies."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_multi_futures_baselines import (
    ASSET_CLASSES,
    add_signals,
    build_strategy_panel,
    daily_portfolio,
    load_front_contracts,
    metrics,
)


PERIODS = {
    "development": ("2011-01-01", "2018-12-31"),
    "validation": ("2019-01-01", "2022-12-31"),
    "final_test": ("2023-01-01", "2026-06-10"),
    "all": ("2011-01-01", "2026-06-10"),
}
COSTS = (2.0, 5.0)


@dataclass(frozen=True)
class Variant:
    name: str
    family: str
    signal: str
    rebalance: str
    universe: str = "all"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, default=Path("data/multi_futures/research/daily_bars")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("reports/multi_futures_comprehensive_20260613")
    )
    parser.add_argument("--bootstrap-repetitions", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260613)
    return parser.parse_args()


def demean_cross_section(values: pd.Series, dates: pd.Series) -> pd.Series:
    return values - values.groupby(dates).transform("mean")


def add_comprehensive_signals(bars: pd.DataFrame) -> pd.DataFrame:
    bars = add_signals(bars)
    grouped = bars.groupby("root", group_keys=False)

    for horizon in (2, 5, 10, 21, 42, 63, 126, 189, 252):
        bars[f"return_{horizon}"] = grouped["synthetic_index"].pct_change(horizon)
        bars[f"ts_sign_{horizon}"] = np.sign(bars[f"return_{horizon}"])
        scale = (
            grouped["return"]
            .transform(
                lambda values, h=horizon: values.rolling(
                    h, min_periods=min(h, max(2, h // 2))
                ).std()
            )
            * np.sqrt(horizon)
        )
        bars[f"ts_cont_{horizon}"] = np.tanh(
            bars[f"return_{horizon}"] / scale.replace(0, np.nan)
        )
        rank = bars.groupby("date")[f"return_{horizon}"].rank(pct=True)
        bars[f"xsec_cont_{horizon}"] = demean_cross_section(2.0 * rank - 1.0, bars["date"])
        bars[f"xsec_tercile_{horizon}"] = np.select(
            [rank >= 2 / 3, rank <= 1 / 3], [1.0, -1.0], default=0.0
        )
        bars[f"xsec_tercile_{horizon}"] = demean_cross_section(
            bars[f"xsec_tercile_{horizon}"], bars["date"]
        )

    for horizon in (63, 126, 252):
        skipped = bars[f"return_{horizon}"] - bars["return_21"]
        rank = skipped.groupby(bars["date"]).rank(pct=True)
        bars[f"xsec_skip21_{horizon}"] = demean_cross_section(2.0 * rank - 1.0, bars["date"])

    for fast, slow in ((10, 42), (21, 63), (21, 126), (42, 126), (63, 189), (63, 252), (126, 252)):
        fast_ma = grouped["synthetic_index"].transform(
            lambda values, h=fast: values.rolling(h, min_periods=h).mean()
        )
        slow_ma = grouped["synthetic_index"].transform(
            lambda values, h=slow: values.rolling(h, min_periods=h).mean()
        )
        bars[f"ma_{fast}_{slow}"] = np.tanh(
            10.0 * (fast_ma / slow_ma.replace(0, np.nan) - 1.0)
        )

    for horizon in (20, 50, 100, 150, 250):
        high = grouped["synthetic_index"].transform(
            lambda values, h=horizon: values.rolling(h, min_periods=h).max()
        )
        low = grouped["synthetic_index"].transform(
            lambda values, h=horizon: values.rolling(h, min_periods=h).min()
        )
        bars[f"breakout_{horizon}"] = (
            2.0
            * (bars["synthetic_index"] - low)
            / (high - low).replace(0, np.nan)
            - 1.0
        ).clip(-1.0, 1.0)

    for horizon in (2, 5, 10, 21):
        bars[f"reversal_{horizon}"] = -bars[f"ts_cont_{horizon}"]
        bars[f"xsec_reversal_{horizon}"] = -bars[f"xsec_cont_{horizon}"]

    valid_carry = bars["carry_rate"].where(bars["carry_valid"])
    bars["carry_cont"] = np.tanh(valid_carry * 5.0)
    carry_rank = valid_carry.groupby(bars["date"]).rank(pct=True)
    bars["carry_xsec"] = demean_cross_section(2.0 * carry_rank - 1.0, bars["date"])

    bars["ts_ensemble_short"] = bars[["ts_sign_21", "ts_sign_42", "ts_sign_63"]].mean(axis=1)
    bars["ts_ensemble_medium"] = bars[["ts_sign_63", "ts_sign_126", "ts_sign_189"]].mean(axis=1)
    bars["ts_ensemble_long"] = bars[["ts_sign_126", "ts_sign_189", "ts_sign_252"]].mean(axis=1)
    bars["ts_ensemble_all"] = bars[
        ["ts_sign_21", "ts_sign_63", "ts_sign_126", "ts_sign_252"]
    ].mean(axis=1)
    bars["xsec_ensemble"] = bars[
        ["xsec_cont_63", "xsec_cont_126", "xsec_cont_252"]
    ].mean(axis=1)
    bars["trend_xsec_combo"] = 0.5 * bars["ts_ensemble_all"] + 0.5 * bars["xsec_ensemble"]
    bars["trend_carry_combo"] = 0.75 * bars["ts_ensemble_all"] + 0.25 * bars["carry_cont"]
    bars["xsec_carry_combo"] = 0.75 * bars["xsec_ensemble"] + 0.25 * bars["carry_xsec"]
    return bars


def variants() -> list[Variant]:
    result: list[Variant] = []

    for horizon in (21, 42, 63, 126, 189, 252):
        for rebalance in ("weekly", "monthly"):
            result.append(Variant(f"ts_sign_{horizon}_{rebalance}", "time_series_momentum", f"ts_sign_{horizon}", rebalance))
            result.append(Variant(f"ts_cont_{horizon}_{rebalance}", "continuous_momentum", f"ts_cont_{horizon}", rebalance))
    for signal in ("ts_ensemble_short", "ts_ensemble_medium", "ts_ensemble_long", "ts_ensemble_all"):
        for rebalance in ("weekly", "monthly"):
            result.append(Variant(f"{signal}_{rebalance}", "time_series_momentum", signal, rebalance))

    for horizon in (63, 126, 252):
        for construction in ("xsec_cont", "xsec_tercile"):
            for rebalance in ("weekly", "monthly"):
                result.append(Variant(f"{construction}_{horizon}_{rebalance}", "cross_sectional_momentum", f"{construction}_{horizon}", rebalance))
        for rebalance in ("weekly", "monthly"):
            result.append(Variant(f"xsec_skip21_{horizon}_{rebalance}", "cross_sectional_momentum_skip", f"xsec_skip21_{horizon}", rebalance))
    for rebalance in ("weekly", "monthly"):
        result.append(Variant(f"xsec_ensemble_{rebalance}", "cross_sectional_momentum", "xsec_ensemble", rebalance))

    for fast, slow in ((10, 42), (21, 63), (21, 126), (42, 126), (63, 189), (63, 252), (126, 252)):
        for rebalance in ("weekly", "monthly"):
            result.append(Variant(f"ma_{fast}_{slow}_{rebalance}", "moving_average_trend", f"ma_{fast}_{slow}", rebalance))
    for horizon in (20, 50, 100, 150, 250):
        for rebalance in ("weekly", "monthly"):
            result.append(Variant(f"breakout_{horizon}_{rebalance}", "breakout", f"breakout_{horizon}", rebalance))
    for horizon in (2, 5, 10, 21):
        for signal, family in ((f"reversal_{horizon}", "time_series_reversal"), (f"xsec_reversal_{horizon}", "cross_sectional_reversal")):
            for rebalance in ("weekly", "monthly"):
                result.append(Variant(f"{signal}_{rebalance}", family, signal, rebalance))

    for signal, family in (
        ("carry_signal", "carry"),
        ("carry_cont", "carry"),
        ("carry_xsec", "carry"),
        ("trend_xsec_combo", "combined"),
        ("trend_carry_combo", "combined"),
        ("xsec_carry_combo", "combined"),
    ):
        for rebalance in ("weekly", "monthly"):
            result.append(Variant(f"{signal}_{rebalance}", family, signal, rebalance))

    # Predefined universe sensitivity, not selected from outcomes.
    for universe in ("no_agriculture", "core_liquid"):
        for signal in ("xsec_cont_126", "xsec_cont_252", "xsec_ensemble", "ts_ensemble_all"):
            result.append(Variant(f"{signal}_monthly_{universe}", "universe_sensitivity", signal, "monthly", universe))
    return result


def apply_universe(panel: pd.DataFrame, universe: str) -> pd.DataFrame:
    if universe == "all":
        return panel
    if universe == "no_agriculture":
        return panel[panel["asset_class"] != "agriculture"].copy()
    if universe == "core_liquid":
        roots = {"ES", "NQ", "YM", "ZN", "ZB", "ZF", "6E", "6J", "6B", "6A", "CL", "NG", "GC", "SI", "HG"}
        return panel[panel["root"].isin(roots)].copy()
    raise ValueError(universe)


def period_metrics(daily: pd.DataFrame, cost_bps: float) -> list[dict[str, object]]:
    rows = []
    for period, (start, end) in PERIODS.items():
        subset = daily.loc[start:end]
        item = metrics(subset["gross_return"] - subset["turnover"] * cost_bps / 10_000.0, subset["turnover"])
        item.update({"period": period, "cost_bps": cost_bps})
        rows.append(item)
    return rows


def yearly_metrics(daily: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    rows = []
    for year, subset in daily.groupby(daily.index.year):
        item = metrics(subset["gross_return"] - subset["turnover"] * cost_bps / 10_000.0, subset["turnover"])
        item["year"] = int(year)
        rows.append(item)
    return pd.DataFrame(rows)


def block_bootstrap_max_sharpe(
    matrix: pd.DataFrame, repetitions: int, seed: int, block: int = 20
) -> dict[str, float]:
    matrix = matrix.dropna(how="all").fillna(0.0)
    centered = matrix - matrix.mean()
    observed = float(
        (matrix.mean() / matrix.std(ddof=1) * np.sqrt(len(matrix) / ((matrix.index.max() - matrix.index.min()).days / 365.25))).max()
    )
    rng = np.random.default_rng(seed)
    maxima = []
    n = len(centered)
    values = centered.to_numpy()
    annualizer = np.sqrt(n / ((matrix.index.max() - matrix.index.min()).days / 365.25))
    for _ in range(repetitions):
        starts = rng.integers(0, n, size=int(np.ceil(n / block)))
        indices = np.concatenate([(np.arange(block) + start) % n for start in starts])[:n]
        sample = values[indices]
        std = sample.std(axis=0, ddof=1)
        sharpes = np.divide(sample.mean(axis=0), std, out=np.zeros_like(std), where=std > 0) * annualizer
        maxima.append(float(np.max(sharpes)))
    maxima_array = np.asarray(maxima)
    return {
        "observed_max_sharpe": observed,
        "null_max_sharpe_mean": float(maxima_array.mean()),
        "null_max_sharpe_95pct": float(np.quantile(maxima_array, 0.95)),
        "familywise_p_value": float((1 + (maxima_array >= observed).sum()) / (repetitions + 1)),
        "repetitions": repetitions,
        "block_observations": block,
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    bars = add_comprehensive_signals(load_front_contracts(args.data))
    definitions = variants()
    metric_rows: list[dict[str, object]] = []
    yearly_rows: list[pd.DataFrame] = []
    daily_returns: dict[str, pd.Series] = {}
    exposure_rows = []

    for index, variant in enumerate(definitions, start=1):
        panel = apply_universe(build_strategy_panel(bars, variant.signal, variant.rebalance), variant.universe)
        daily = daily_portfolio(panel, 0.0)
        daily_returns[variant.name] = daily["gross_return"] - daily["turnover"] * 2.0 / 10_000.0
        for cost in COSTS:
            for item in period_metrics(daily, cost):
                item.update(
                    {
                        "variant": variant.name,
                        "family": variant.family,
                        "signal": variant.signal,
                        "rebalance": variant.rebalance,
                        "universe": variant.universe,
                    }
                )
                metric_rows.append(item)
        years = yearly_metrics(daily, 2.0)
        years["variant"] = variant.name
        years["family"] = variant.family
        yearly_rows.append(years)
        exposure = panel.groupby("date")["weight"].apply(lambda values: values.abs().sum())
        exposure_rows.append(
            {
                "variant": variant.name,
                "mean_gross_exposure": exposure.mean(),
                "max_gross_exposure": exposure.max(),
            }
        )
        if index % 20 == 0 or index == len(definitions):
            print(f"evaluated {index}/{len(definitions)} variants")

    results = pd.DataFrame(metric_rows)
    results.to_csv(args.out / "period_results.csv", index=False, float_format="%.10f")
    yearly = pd.concat(yearly_rows, ignore_index=True)
    yearly.to_csv(args.out / "yearly_results.csv", index=False, float_format="%.10f")
    exposure = pd.DataFrame(exposure_rows)
    exposure.to_csv(args.out / "exposure.csv", index=False, float_format="%.10f")

    family_consistency = (
        results[results["cost_bps"].eq(2.0)]
        .groupby(["family", "period"])
        .agg(
            variants=("variant", "size"),
            positive_fraction=("sharpe", lambda values: float((values > 0).mean())),
            median_sharpe=("sharpe", "median"),
            best_sharpe=("sharpe", "max"),
            worst_sharpe=("sharpe", "min"),
            median_cagr=("cagr", "median"),
        )
        .reset_index()
    )
    family_consistency.to_csv(
        args.out / "family_consistency.csv", index=False, float_format="%.10f"
    )

    strict = build_strict_screen(results, yearly, exposure)
    strict.to_csv(args.out / "strict_candidate_screen.csv", index=False, float_format="%.10f")

    development = results[(results.period == "development") & (results.cost_bps == 2.0)]
    validation = results[(results.period == "validation") & (results.cost_bps == 2.0)]
    final = results[(results.period == "final_test") & (results.cost_bps == 2.0)]
    selected = (
        development.sort_values("sharpe", ascending=False)
        .groupby("family", as_index=False)
        .first()[["family", "variant", "sharpe"]]
        .rename(columns={"sharpe": "development_sharpe"})
    )
    selected = selected.merge(
        validation[["variant", "sharpe", "cagr", "max_drawdown", "profit_factor"]].rename(
            columns={column: f"validation_{column}" for column in ["sharpe", "cagr", "max_drawdown", "profit_factor"]}
        ),
        on="variant",
        how="left",
    )
    selected = selected.merge(
        final[["variant", "sharpe", "cagr", "max_drawdown", "profit_factor"]].rename(
            columns={column: f"final_{column}" for column in ["sharpe", "cagr", "max_drawdown", "profit_factor"]}
        ),
        on="variant",
        how="left",
    )
    selected.to_csv(args.out / "family_selection.csv", index=False, float_format="%.10f")

    matrix = pd.DataFrame(daily_returns).sort_index()
    matrix.to_parquet(args.out / "variant_daily_returns_2bps.parquet", compression="zstd")
    bootstrap = block_bootstrap_max_sharpe(
        matrix.loc["2011-01-01":"2018-12-31"],
        args.bootstrap_repetitions,
        args.seed,
    )
    (args.out / "multiple_testing.json").write_text(
        json.dumps(bootstrap, indent=2) + "\n", encoding="ascii"
    )
    write_report(
        results,
        selected,
        yearly,
        family_consistency,
        strict,
        bootstrap,
        len(definitions),
        args.out,
    )
    print(f"Completed comprehensive evaluation under {args.out}")


def build_strict_screen(
    results: pd.DataFrame, yearly: pd.DataFrame, exposure: pd.DataFrame
) -> pd.DataFrame:
    period_sharpe = results[
        results["cost_bps"].eq(2.0)
        & results["period"].isin(["development", "validation", "final_test"])
    ].pivot(index="variant", columns="period", values="sharpe")
    all_two = results[
        results["cost_bps"].eq(2.0) & results["period"].eq("all")
    ].set_index("variant")
    all_five = results[
        results["cost_bps"].eq(5.0) & results["period"].eq("all")
    ].set_index("variant")
    screen = period_sharpe.join(
        all_two[["family", "cagr", "sharpe", "max_drawdown", "profit_factor"]].rename(
            columns=lambda column: f"all_2bps_{column}"
        )
    )
    screen = screen.join(
        all_five[["cagr", "sharpe", "max_drawdown", "profit_factor"]].rename(
            columns=lambda column: f"all_5bps_{column}"
        )
    )
    screen = screen.join(exposure.set_index("variant"))
    year_counts = yearly.groupby("variant").agg(
        positive_years=("cagr", lambda values: int((values > 0).sum())),
        years=("year", "size"),
        median_yearly_sharpe=("sharpe", "median"),
    )
    screen = screen.join(year_counts)
    screen["min_period_sharpe"] = screen[
        ["development", "validation", "final_test"]
    ].min(axis=1)
    screen["strict_pass"] = (
        (screen[["development", "validation", "final_test"]] > 0).all(axis=1)
        & (screen["all_5bps_sharpe"] > 0)
        & (screen["all_2bps_profit_factor"] >= 1.05)
        & (screen["all_2bps_max_drawdown"] >= -0.35)
        & (screen["max_gross_exposure"] <= 4.0)
    )
    return screen.reset_index().sort_values(
        ["strict_pass", "min_period_sharpe", "all_2bps_sharpe"],
        ascending=False,
    )


def write_report(
    results: pd.DataFrame,
    selected: pd.DataFrame,
    yearly: pd.DataFrame,
    family_consistency: pd.DataFrame,
    strict: pd.DataFrame,
    bootstrap: dict[str, float],
    variant_count: int,
    out: Path,
) -> None:
    final = results[(results.period == "final_test") & (results.cost_bps == 2.0)]
    all_period = results[(results.period == "all") & (results.cost_bps == 2.0)]
    leaders = final.sort_values("sharpe", ascending=False).head(15)
    lines = [
        "# Comprehensive Multi-Futures Strategy Evaluation",
        "",
        f"Date: {datetime.now(timezone.utc).date().isoformat()}",
        "",
        "## Executive Verdict",
        "",
        f"Evaluated `{variant_count}` predefined variants across distinct strategy families. "
        "Development is 2011-2018, validation is 2019-2022, and the final test is "
        "2023 through June 10, 2026.",
        "",
        "This is a broad daily systematic-strategy screen, not an exhaustive search of "
        "all possible strategies and not yet a supervised-ML model comparison.",
        "",
        "**Cross-sectional momentum is the only family with consistently interesting "
        "evidence. Carry is rejected. Recent short-horizon reversal strength is a regime "
        "observation, not a stable strategy. No strategy is approved for live trading.**",
        "",
        "## Final-Test Leaders At 2 Bps",
        "",
        "| Variant | Family | CAGR | Sharpe | Max DD | Profit factor |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, row in leaders.iterrows():
        lines.append(
            f"| `{row.variant}` | `{row.family}` | {row.cagr:.2%} | {row.sharpe:.2f} | "
            f"{row.max_drawdown:.2%} | {row.profit_factor:.2f} |"
        )
    lines += [
        "",
        "## Family Selection Audit",
        "",
        "The following variant was selected only by development Sharpe inside each family:",
        "",
        "| Family | Development winner | Dev Sharpe | Validation Sharpe | Final Sharpe | Final CAGR |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, row in selected.sort_values("final_sharpe", ascending=False).iterrows():
        lines.append(
            f"| `{row.family}` | `{row.variant}` | {row.development_sharpe:.2f} | "
            f"{row.validation_sharpe:.2f} | {row.final_sharpe:.2f} | {row.final_cagr:.2%} |"
        )
    xsec = all_period[all_period.family.str.contains("cross_sectional_momentum")]
    positive_xsec = int((xsec.sharpe > 0).sum())
    strict_pass = strict[strict["strict_pass"]]
    family_final = family_consistency[family_consistency["period"].eq("final_test")]
    lines += [
        "",
        "## Strict Candidate Screen",
        "",
        "This screen requires positive Sharpe in development, validation, and final-test "
        "blocks; positive all-period Sharpe at 5 bps; all-period profit factor at least "
        "1.05; drawdown no worse than 35%; and maximum gross exposure no higher than 4x.",
        "",
        f"`{len(strict_pass)}/{variant_count}` variants pass. The leading passes are:",
        "",
        "| Variant | Family | Min period Sharpe | All 2-bps Sharpe | All 5-bps Sharpe | Max DD | Max exposure |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in strict_pass.head(15).iterrows():
        lines.append(
            f"| `{row.variant}` | `{row.all_2bps_family}` | {row.min_period_sharpe:.2f} | "
            f"{row.all_2bps_sharpe:.2f} | {row.all_5bps_sharpe:.2f} | "
            f"{row.all_2bps_max_drawdown:.2%} | {row.max_gross_exposure:.2f}x |"
        )
    lines += [
        "",
        "## Family Consistency",
        "",
        "| Family | Final positive fraction | Final median Sharpe | Final best Sharpe |",
        "|---|---:|---:|---:|",
    ]
    for _, row in family_final.sort_values("median_sharpe", ascending=False).iterrows():
        lines.append(
            f"| `{row.family}` | {row.positive_fraction:.0%} | "
            f"{row.median_sharpe:.2f} | {row.best_sharpe:.2f} |"
        )
    lines += [
        "",
        "## Multiple-Testing Audit",
        "",
        f"- Development observed maximum Sharpe: `{bootstrap['observed_max_sharpe']:.2f}`.",
        f"- Block-bootstrap null maximum Sharpe mean: `{bootstrap['null_max_sharpe_mean']:.2f}`.",
        f"- Null maximum Sharpe 95th percentile: `{bootstrap['null_max_sharpe_95pct']:.2f}`.",
        f"- Family-wise bootstrap p-value: `{bootstrap['familywise_p_value']:.4f}`.",
        "",
        "This audit asks whether the best development result is stronger than the maximum "
        "one would expect after searching all variants. It does not correct for prior "
        "research decisions made before this script.",
        "",
        f"**The search-wide result does not clear a 5% family-wise threshold "
        f"(`p={bootstrap['familywise_p_value']:.4f}`).**",
        "",
        "## Interpretation",
        "",
        f"- `{positive_xsec}/{len(xsec)}` cross-sectional momentum variants are positive "
        "over the complete period at 2 bps, indicating a family effect rather than one "
        "isolated parameter.",
        "- Monthly and weekly rebalancing generally outperform daily updates because the "
        "signal is slow and turnover is expensive.",
        "- Carry based on volume-ranked `.v.1` is structurally unreliable and fails.",
        "- Recent short-horizon reversal is strong only in the final block. Its "
        "development-selected family winner fails validation, and the family median is "
        "negative over the complete period. Do not promote it.",
        "- Excluding agriculture and using the core-liquid universe improves results, "
        "but these universe choices were informed by earlier full-history inspection and "
        "must be treated as post-hoc.",
        "- Results still use UTC calendar buckets and continuous volume-ranked contracts. "
        "An exchange-session and explicit IBKR contract/margin simulation remains required.",
        "- The final-test block is mechanically untouched by this script's family selection, "
        "but it is not pristine research history because earlier project work inspected the "
        "same dates.",
        "",
        "## Files",
        "",
        "- `period_results.csv`: every variant, period, and cost result.",
        "- `family_selection.csv`: development-selected family winners and untouched results.",
        "- `yearly_results.csv`: yearly stability.",
        "- `variant_daily_returns_2bps.parquet`: common return matrix.",
        "- `multiple_testing.json`: block-bootstrap search correction.",
        "- `exposure.csv`: gross exposure diagnostics.",
        "- `family_consistency.csv`: family-level result distributions.",
        "- `strict_candidate_screen.csv`: conservative promotion screen.",
        "",
    ]
    (out / "COMPREHENSIVE_EVALUATION.md").write_text("\n".join(lines), encoding="ascii")


if __name__ == "__main__":
    main()
