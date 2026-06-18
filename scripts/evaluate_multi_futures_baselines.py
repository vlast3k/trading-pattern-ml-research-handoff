#!/usr/bin/env python3
"""Evaluate conservative roll-safe daily multi-futures portfolio baselines."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ASSET_CLASSES = {
    "ES": "equity_index",
    "NQ": "equity_index",
    "RTY": "equity_index",
    "YM": "equity_index",
    "ZN": "rates",
    "ZB": "rates",
    "ZF": "rates",
    "6E": "fx",
    "6J": "fx",
    "6B": "fx",
    "6A": "fx",
    "CL": "energy",
    "NG": "energy",
    "GC": "metals",
    "SI": "metals",
    "HG": "metals",
    "ZC": "agriculture",
    "ZW": "agriculture",
    "ZS": "agriculture",
    "LE": "livestock",
}
TRADING_DAYS = 252
INDIVIDUAL_VOL_TARGET = 0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, default=Path("data/multi_futures/research/daily_bars")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("reports/multi_futures_baseline_20260613")
    )
    return parser.parse_args()


def load_front_contracts(path: Path) -> pd.DataFrame:
    bars = pd.concat(
        [pd.read_parquet(file) for file in sorted(path.glob("*.parquet"))],
        ignore_index=True,
    )
    carry = bars.pivot_table(
        index=["date", "root"],
        columns="continuous_rank",
        values=["close", "expiration"],
        aggfunc="last",
    ).reset_index()
    carry.columns = [
        f"{first}_{second}" if second != "" else first
        for first, second in carry.columns.to_flat_index()
    ]
    expiry_days = (
        pd.to_datetime(carry["expiration_1"], utc=True)
        - pd.to_datetime(carry["expiration_0"], utc=True)
    ).dt.total_seconds() / 86400.0
    valid_carry = (
        (expiry_days > 0)
        & (carry["close_0"] > 0)
        & (carry["close_1"] > 0)
    )
    carry["carry_rate"] = np.where(
        valid_carry,
        np.log(carry["close_0"] / carry["close_1"]) * 365.0 / expiry_days,
        np.nan,
    )
    carry["carry_signal"] = np.sign(carry["carry_rate"])
    carry["carry_valid"] = valid_carry

    bars = bars[bars["continuous_rank"] == 0].copy()
    bars = bars.merge(
        carry[["date", "root", "carry_rate", "carry_signal", "carry_valid"]],
        on=["date", "root"],
        how="left",
    )
    bars["asset_class"] = bars["root"].map(ASSET_CLASSES)
    bars = bars.sort_values(["root", "date"]).reset_index(drop=True)

    grouped = bars.groupby("root", group_keys=False)
    bars["previous_close"] = grouped["close"].shift()
    bars["previous_instrument_id"] = grouped["instrument_id"].shift()
    bars["is_roll"] = (
        bars["previous_instrument_id"].notna()
        & (bars["instrument_id"] != bars["previous_instrument_id"])
    )
    same_contract_return = bars["close"] / bars["previous_close"] - 1.0
    roll_day_return = bars["close"] / bars["open"] - 1.0
    bars["return"] = same_contract_return.where(~bars["is_roll"], roll_day_return)
    bars.loc[bars["previous_close"].isna(), "return"] = np.nan
    bars["return"] = bars["return"].where(bars["return"].abs() <= 0.50)
    bars["synthetic_index"] = grouped["return"].transform(
        lambda values: (1.0 + values.fillna(0.0)).cumprod()
    )
    bars["vol_60"] = grouped["return"].transform(
        lambda values: values.rolling(60, min_periods=40).std()
        * np.sqrt(TRADING_DAYS)
    )
    return bars


def add_signals(bars: pd.DataFrame) -> pd.DataFrame:
    grouped = bars.groupby("root", group_keys=False)
    momentum_signals = []
    breakout_signals = []
    for horizon in (21, 63, 126, 252):
        momentum = grouped["synthetic_index"].pct_change(horizon)
        momentum_signals.append(np.sign(momentum))
    for horizon in (50, 100, 250):
        rolling_high = grouped["synthetic_index"].transform(
            lambda values, h=horizon: values.rolling(h, min_periods=h).max()
        )
        rolling_low = grouped["synthetic_index"].transform(
            lambda values, h=horizon: values.rolling(h, min_periods=h).min()
        )
        location = (
            2.0
            * (bars["synthetic_index"] - rolling_low)
            / (rolling_high - rolling_low).replace(0, np.nan)
            - 1.0
        )
        breakout_signals.append(location.clip(-1.0, 1.0))
    bars["ts_momentum_signal"] = pd.concat(momentum_signals, axis=1).mean(axis=1)
    bars["breakout_signal"] = pd.concat(breakout_signals, axis=1).mean(axis=1)

    bars["momentum_252"] = grouped["synthetic_index"].pct_change(252)
    bars["xsec_rank"] = bars.groupby("date")["momentum_252"].rank(pct=True)
    raw_xsec_signal = 2.0 * bars["xsec_rank"] - 1.0
    bars["xsec_momentum_signal"] = (
        raw_xsec_signal - raw_xsec_signal.groupby(bars["date"]).transform("mean")
    ).where(
        bars.groupby("date")["momentum_252"].transform("count") >= 10
    )
    bars["combined_signal"] = (
        0.5 * bars["ts_momentum_signal"] + 0.5 * bars["xsec_momentum_signal"]
    )
    bars["combined_trend_carry_signal"] = (
        0.5 * bars["ts_momentum_signal"] + 0.5 * bars["carry_signal"]
    )
    return bars


def build_strategy_panel(
    bars: pd.DataFrame, signal_column: str, rebalance: str = "daily"
) -> pd.DataFrame:
    frame = bars.copy()
    frame["signal"] = frame.groupby("root")[signal_column].shift()
    frame["ex_ante_vol"] = frame.groupby("root")["vol_60"].shift()
    frame["forecast_weight"] = (
        frame["signal"]
        * INDIVIDUAL_VOL_TARGET
        / frame["ex_ante_vol"].clip(lower=0.05)
    ).clip(-2.0, 2.0)
    if rebalance != "daily":
        frequency = {"weekly": "W-FRI", "monthly": "M"}[rebalance]
        period = frame["date"].dt.tz_localize(None).dt.to_period(frequency)
        previous_period = period.groupby(frame["root"]).shift()
        frame["forecast_weight"] = frame["forecast_weight"].where(
            period != previous_period
        )
        frame["forecast_weight"] = frame.groupby("root")["forecast_weight"].ffill()
    active = frame.groupby("date")["forecast_weight"].transform(
        lambda values: values.notna().sum()
    )
    frame["weight"] = frame["forecast_weight"] / np.sqrt(active.replace(0, np.nan))
    frame["previous_weight"] = frame.groupby("root")["weight"].shift().fillna(0.0)
    frame["turnover"] = (frame["weight"] - frame["previous_weight"]).abs()
    # Rolling an unchanged position requires closing the old and opening the new contract.
    frame["roll_turnover"] = np.where(
        frame["is_roll"], 2.0 * frame["previous_weight"].abs(), 0.0
    )
    frame["total_turnover"] = frame["turnover"] + frame["roll_turnover"]
    frame["gross_contribution"] = frame["weight"] * frame["return"]
    return frame


def daily_portfolio(panel: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    daily = (
        panel.groupby("date")
        .agg(
            gross_return=("gross_contribution", "sum"),
            turnover=("total_turnover", "sum"),
            active_markets=("weight", "count"),
        )
        .sort_index()
    )
    daily["cost"] = daily["turnover"] * cost_bps / 10_000.0
    daily["net_return"] = daily["gross_return"] - daily["cost"]
    return daily[daily["active_markets"] > 0]


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns.fillna(0.0)).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def metrics(returns: pd.Series, turnover: pd.Series) -> dict[str, float]:
    values = returns.dropna()
    equity = (1.0 + values).cumprod()
    if isinstance(values.index, pd.DatetimeIndex) and len(values) > 1:
        years = max((values.index.max() - values.index.min()).days / 365.25, 1 / 365.25)
        periods_per_year = len(values) / years
    else:
        years = len(values) / TRADING_DAYS
        periods_per_year = TRADING_DAYS
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else np.nan
    annual_vol = float(values.std(ddof=1) * np.sqrt(periods_per_year))
    sharpe = (
        float(values.mean() / values.std(ddof=1) * np.sqrt(periods_per_year))
        if values.std(ddof=1) > 0
        else np.nan
    )
    downside = values[values < 0].std(ddof=1)
    sortino = (
        float(values.mean() / downside * np.sqrt(periods_per_year))
        if downside > 0
        else np.nan
    )
    drawdown = max_drawdown(values)
    gains = values[values > 0]
    losses = values[values < 0]
    return {
        "days": len(values),
        "observations_per_year": periods_per_year,
        "cagr": cagr,
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": drawdown,
        "calmar": cagr / abs(drawdown) if drawdown < 0 else np.nan,
        "positive_day_rate": float((values > 0).mean()),
        "average_positive_day": float(gains.mean()) if len(gains) else np.nan,
        "average_negative_day": float(losses.mean()) if len(losses) else np.nan,
        "payoff_ratio": float(gains.mean() / abs(losses.mean()))
        if len(gains) and len(losses)
        else np.nan,
        "profit_factor": float(gains.sum() / abs(losses.sum()))
        if len(losses) and losses.sum() != 0
        else np.nan,
        "average_daily_turnover": float(turnover.mean()),
        "total_return": float(equity.iloc[-1] - 1.0),
    }


def robustness_tables(
    strategy: str, panel: pd.DataFrame, daily: pd.DataFrame, cost_bps: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    by_year = []
    for year, rows in daily.groupby(daily.index.year):
        item = metrics(rows["net_return"], rows["turnover"])
        item.update({"strategy": strategy, "cost_bps": cost_bps, "year": int(year)})
        by_year.append(item)

    by_market = []
    for root, rows in panel.groupby("root"):
        contribution = rows.set_index("date")["gross_contribution"]
        cost = rows.set_index("date")["total_turnover"] * cost_bps / 10_000.0
        item = metrics(contribution - cost, rows.set_index("date")["total_turnover"])
        item.update(
            {
                "strategy": strategy,
                "cost_bps": cost_bps,
                "root": root,
                "asset_class": ASSET_CLASSES[root],
            }
        )
        by_market.append(item)

    by_asset_class = []
    for asset_class, rows in panel.groupby("asset_class"):
        grouped = rows.groupby("date").agg(
            gross_return=("gross_contribution", "sum"),
            turnover=("total_turnover", "sum"),
        )
        item = metrics(
            grouped["gross_return"] - grouped["turnover"] * cost_bps / 10_000.0,
            grouped["turnover"],
        )
        item.update(
            {
                "strategy": strategy,
                "cost_bps": cost_bps,
                "asset_class": asset_class,
            }
        )
        by_asset_class.append(item)
    return pd.DataFrame(by_year), pd.DataFrame(by_market), pd.DataFrame(by_asset_class)


def leave_one_out(strategy: str, panel: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    rows = []
    for root in sorted(panel["root"].unique()):
        subset = panel[panel["root"] != root]
        daily = daily_portfolio(subset, cost_bps)
        item = metrics(daily["net_return"], daily["turnover"])
        item.update({"strategy": strategy, "cost_bps": cost_bps, "removed_root": root})
        rows.append(item)
    for year in sorted(panel["date"].dt.year.unique()):
        subset = panel[panel["date"].dt.year != year]
        daily = daily_portfolio(subset, cost_bps)
        item = metrics(daily["net_return"], daily["turnover"])
        item.update(
            {"strategy": strategy, "cost_bps": cost_bps, "removed_year": int(year)}
        )
        rows.append(item)
    return pd.DataFrame(rows)


def write_verdict(summary: pd.DataFrame, out: Path) -> None:
    base = summary[summary["cost_bps"] == 2.0].sort_values("sharpe", ascending=False)
    best = base.iloc[0]
    best_five_bps = summary[
        (summary["strategy"] == best.strategy) & (summary["cost_bps"] == 5.0)
    ].iloc[0]
    years = pd.read_csv(out / "by_year.csv")
    best_years = years[years["strategy"] == best.strategy]
    assets = pd.read_csv(out / "by_asset_class.csv")
    best_assets = assets[assets["strategy"] == best.strategy]
    leave = pd.read_csv(out / "leave_one_out.csv")
    best_leave = leave[leave["strategy"] == best.strategy]
    panel = pd.read_parquet(out / f"{best.strategy}_panel.parquet")
    gross_exposure = panel.groupby("date")["weight"].apply(lambda values: values.abs().sum())
    best_daily = pd.read_csv(
        out / f"{best.strategy}_daily_2bps.csv", parse_dates=["date"]
    ).set_index("date")
    monthly = (1.0 + best_daily["net_return"]).groupby(
        best_daily.index.tz_localize(None).to_period("M")
    ).prod() - 1.0
    monthly_winners = monthly[monthly > 0]
    monthly_losers = monthly[monthly < 0]
    monthly_payoff = monthly_winners.mean() / abs(monthly_losers.mean())
    monthly_profit_factor = monthly_winners.sum() / abs(monthly_losers.sum())
    positive_years = int((best_years["cagr"] > 0).sum())
    positive_assets = int((best_assets["cagr"] > 0).sum())
    min_leave_root = best_leave[best_leave["removed_root"].notna()]["sharpe"].min()
    min_leave_year = best_leave[best_leave["removed_year"].notna()]["sharpe"].min()
    lines = [
        "# Multi-Futures Baseline Evaluation",
        "",
        f"Date: {datetime.now(timezone.utc).date().isoformat()}",
        "",
        "## Design",
        "",
        "- Uses only volume-ranked front contracts (`.v.0`).",
        "- Signals are computed from a roll-safe synthetic return index and delayed one day.",
        "- Same-contract days use close-to-close return; roll days use new-contract open-to-close return.",
        "- Positions are volatility-scaled and divided by the square root of active markets.",
        "- Roll turnover explicitly charges closing the old and opening the new contract.",
        "- Results include gross and `1`, `2`, and `5` basis-point one-way turnover costs.",
        "- Daily, weekly, and monthly rebalance variants use identical signals; only "
        "the target-position update frequency changes.",
        "- Databento daily bars are UTC calendar buckets, not exchange-session bars. "
        "Annualization uses actual elapsed calendar time.",
        "",
        "## Main Results At 2 Bps",
        "",
        "| Strategy | CAGR | Sharpe | Max DD | Profit factor | Payoff ratio | Avg daily turnover |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in base.iterrows():
        lines.append(
            f"| `{row.strategy}` | {row.cagr:.2%} | {row.sharpe:.2f} | "
            f"{row.max_drawdown:.2%} | {row.profit_factor:.2f} | "
            f"{row.payoff_ratio:.2f} | {row.average_daily_turnover:.3f} |"
        )
    lines += [
        "",
        "## Initial Verdict",
        "",
        f"The strongest 2-bps baseline is `{best.strategy}` with Sharpe "
        f"`{best.sharpe:.2f}`, CAGR `{best.cagr:.2%}`, and maximum drawdown "
        f"`{best.max_drawdown:.2%}`.",
        "",
        "**Verdict: retain as the lead research baseline, but do not approve it for live "
        "trading or treat it as an independent confirmation.**",
        "",
        f"- It remains positive at 5 bps one-way cost: CAGR `{best_five_bps.cagr:.2%}`, "
        f"Sharpe `{best_five_bps.sharpe:.2f}`.",
        f"- Positive calendar years at 2 bps: `{positive_years}/{len(best_years)}`.",
        f"- Positive asset classes at 2 bps: `{positive_assets}/{len(best_assets)}`.",
        f"- Worst leave-one-market-out Sharpe: `{min_leave_root:.2f}`; worst "
        f"leave-one-year-out Sharpe: `{min_leave_year:.2f}`.",
        f"- Monthly payoff ratio: `{monthly_payoff:.2f}` and monthly profit factor: "
        f"`{monthly_profit_factor:.2f}`. Daily payoff ratio remains below one.",
        f"- Average gross exposure is `{gross_exposure.mean():.2f}x`; maximum is "
        f"`{gross_exposure.max():.2f}x`, before explicit IBKR margin constraints.",
        "",
        "The main weaknesses are material: drawdown remains about 30%, agriculture is "
        "negative, UTC daily buckets are not exchange sessions, and the monthly variant "
        "was selected after inspecting the same historical sample. The naive carry "
        "baseline is rejected.",
        "",
        "The next promotion review requires an exchange-session panel, explicit margin "
        "and contract sizing, frozen monthly cross-sectional rules, and an untouched "
        "forward or later-contract test. ML should be evaluated only as a challenger to "
        "this baseline, with turnover penalties built into the target.",
        "",
        "See `summary.csv`, `by_year.csv`, `by_market.csv`, `by_asset_class.csv`, "
        "`leave_one_out.csv`, and per-strategy daily return files for the audit trail.",
        "",
    ]
    (out / "VERDICT.md").write_text("\n".join(lines), encoding="ascii")


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    bars = add_signals(load_front_contracts(args.data))
    bars.to_parquet(args.out / "roll_safe_panel.parquet", index=False, compression="zstd")

    strategies = {
        "time_series_momentum": ("ts_momentum_signal", "daily"),
        "time_series_momentum_weekly": ("ts_momentum_signal", "weekly"),
        "time_series_momentum_monthly": ("ts_momentum_signal", "monthly"),
        "breakout_location": ("breakout_signal", "daily"),
        "cross_sectional_momentum": ("xsec_momentum_signal", "daily"),
        "cross_sectional_momentum_weekly": ("xsec_momentum_signal", "weekly"),
        "cross_sectional_momentum_monthly": ("xsec_momentum_signal", "monthly"),
        "combined_trend_xsec": ("combined_signal", "daily"),
        "combined_trend_xsec_weekly": ("combined_signal", "weekly"),
        "carry_sign": ("carry_signal", "daily"),
        "carry_sign_monthly": ("carry_signal", "monthly"),
        "combined_trend_carry": ("combined_trend_carry_signal", "daily"),
        "combined_trend_carry_monthly": ("combined_trend_carry_signal", "monthly"),
    }
    summary_rows = []
    year_tables = []
    market_tables = []
    asset_tables = []
    leave_tables = []
    for strategy, (signal, rebalance) in strategies.items():
        panel = build_strategy_panel(bars, signal, rebalance)
        panel.to_parquet(
            args.out / f"{strategy}_panel.parquet", index=False, compression="zstd"
        )
        for cost_bps in (0.0, 1.0, 2.0, 5.0):
            daily = daily_portfolio(panel, cost_bps)
            daily.to_csv(
                args.out / f"{strategy}_daily_{cost_bps:g}bps.csv",
                float_format="%.10f",
            )
            item = metrics(daily["net_return"], daily["turnover"])
            item.update({"strategy": strategy, "cost_bps": cost_bps})
            summary_rows.append(item)
            if cost_bps == 2.0:
                by_year, by_market, by_asset = robustness_tables(
                    strategy, panel, daily, cost_bps
                )
                year_tables.append(by_year)
                market_tables.append(by_market)
                asset_tables.append(by_asset)
                leave_tables.append(leave_one_out(strategy, panel, cost_bps))
        print(f"evaluated {strategy}")

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(args.out / "summary.csv", index=False, float_format="%.10f")
    pd.concat(year_tables, ignore_index=True).to_csv(
        args.out / "by_year.csv", index=False, float_format="%.10f"
    )
    pd.concat(market_tables, ignore_index=True).to_csv(
        args.out / "by_market.csv", index=False, float_format="%.10f"
    )
    pd.concat(asset_tables, ignore_index=True).to_csv(
        args.out / "by_asset_class.csv", index=False, float_format="%.10f"
    )
    pd.concat(leave_tables, ignore_index=True).to_csv(
        args.out / "leave_one_out.csv", index=False, float_format="%.10f"
    )
    config = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "individual_vol_target": INDIVIDUAL_VOL_TARGET,
        "signal_delay_days": 1,
        "cost_sensitivity_bps_one_way": [0, 1, 2, 5],
        "rebalance_variants": ["daily", "weekly", "monthly"],
        "asset_classes": ASSET_CLASSES,
        "roll_return": "new contract open-to-close",
        "same_contract_return": "close-to-close",
    }
    (args.out / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="ascii"
    )
    write_verdict(summary, args.out)
    print(f"Completed baseline evaluation under {args.out}")


if __name__ == "__main__":
    main()
