#!/usr/bin/env python3
"""Leak-aware historical analog and supervised ML baselines for canonical MNQ data."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression as SklearnLogisticRegression

    SKLEARN_AVAILABLE = True
except ImportError:
    HistGradientBoostingClassifier = None
    SklearnLogisticRegression = None
    SKLEARN_AVAILABLE = False


UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")
POINT_VALUE = 2.0
TICK_SIZE = 0.25
FORMULA_VARIANT = "vwap_delta_rejection"

CANONICAL_COLUMNS = [
    "second",
    "trade_source",
    "quote_source",
    "depth_source",
    "trade_count",
    "trade_volume",
    "buy_volume",
    "sell_volume",
    "trade_open",
    "trade_high",
    "trade_low",
    "trade_close",
    "quote_updates",
    "last_bid",
    "last_ask",
    "last_spread",
    "depth_rows",
    "last_depth_bid_total",
    "last_depth_ask_total",
    "last_depth_imbalance",
    "bid_p0_volume",
    "bid_p1_volume",
    "bid_p2_volume",
    "bid_p7_volume",
    "bid_p8_volume",
    "bid_p9_volume",
    "ask_p0_volume",
    "ask_p1_volume",
    "ask_p2_volume",
    "ask_p7_volume",
    "ask_p8_volume",
    "ask_p9_volume",
]

MODEL_FEATURES = [
    "direction",
    "signed_ret_1m",
    "signed_ret_5m",
    "signed_ret_15m",
    "signed_ret_60m",
    "rv_15m_atr",
    "range_1m_atr",
    "signed_dist_vwap_atr",
    "signed_dist_high_15_atr",
    "signed_dist_low_15_atr",
    "signed_dist_high_60_atr",
    "signed_dist_low_60_atr",
    "volume_ratio_20",
    "trades_ratio_20",
    "signed_delta_pct",
    "signed_delta_ratio_20",
    "spread_atr",
    "spread_vol_20",
    "quote_ratio_20",
    "signed_depth_imbalance",
    "signed_depth_imbalance_change",
    "signed_depth_imbalance_persist_10",
    "depth_ratio_20",
    "signed_book_slope",
    "minute_sin",
    "minute_cos",
    "is_rth",
    "is_rth_open",
    "is_rth_close",
    "signed_nq_ret_1m",
    "signed_nq_ret_5m",
    "signed_mnq_nq_div_1m",
    "signed_nq_delta_pct",
    "signed_nq_depth_imbalance",
    "formula_signal",
]

ANALOG_FEATURES = [
    "signed_ret_1m",
    "signed_ret_5m",
    "signed_ret_15m",
    "signed_ret_60m",
    "rv_15m_atr",
    "range_1m_atr",
    "signed_dist_vwap_atr",
    "volume_ratio_20",
    "signed_delta_pct",
    "spread_atr",
    "signed_depth_imbalance",
    "signed_depth_imbalance_persist_10",
    "signed_book_slope",
    "signed_nq_ret_5m",
    "signed_mnq_nq_div_1m",
    "formula_signal",
]

WALK_FORWARD_FOLDS = [
    ("wf_1", "2026-04-01", "2026-04-17", "2026-04-20", "2026-04-24"),
    ("wf_2", "2026-04-01", "2026-04-24", "2026-04-27", "2026-05-01"),
    ("wf_3", "2026-04-01", "2026-05-01", "2026-05-04", "2026-05-08"),
    ("wf_4", "2026-04-01", "2026-05-08", "2026-05-11", "2026-05-15"),
]


@dataclass(frozen=True)
class ResearchConfig:
    canonical_dir: Path
    baseline_trades: Path
    out_dir: Path
    decision_interval_minutes: int = 5
    horizon_minutes: int = 30
    stop_atr: float = 1.0
    target_r: float = 2.0
    min_stop_points: float = 1.0
    commission_round_turn: float = 3.98
    slippage_ticks_per_side: float = 1.0
    analog_neighbors: int = 25
    seed: int = 20260612

    @property
    def fixed_cost_dollars(self) -> float:
        return self.commission_round_turn + (
            2.0 * self.slippage_ticks_per_side * TICK_SIZE * POINT_VALUE
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical-dir",
        type=Path,
        default=Path("data/canonical_orderflow_1s"),
    )
    parser.add_argument(
        "--baseline-trades",
        type=Path,
        default=Path("reports/canonical_corrected_20260611/mnq_06_26_trades.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/pattern_ml_20260612"),
    )
    parser.add_argument("--decision-interval-minutes", type=int, default=5)
    parser.add_argument("--horizon-minutes", type=int, default=30)
    parser.add_argument("--analog-neighbors", type=int, default=25)
    parser.add_argument("--rebuild-cache", action="store_true")
    return parser.parse_args()


def partition_date(path: Path) -> str:
    match = re.search(r"_(\d{8})_1s\.csv\.gz$", path.name)
    if not match:
        raise ValueError(f"cannot parse partition date: {path}")
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def verify_manifest(canonical_dir: Path) -> dict:
    manifest_path = canonical_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if int(manifest.get("version", 0)) < 3:
        raise ValueError("canonical manifest version must be 3 or newer")
    partitions = manifest.get("partitions", [])
    summary: dict[str, dict[str, int]] = {}
    for row in partitions:
        name = row["file"]
        match = re.match(r"canonical_([a-z]+)_", name)
        if not match:
            continue
        instrument = match.group(1).upper()
        rec = summary.setdefault(instrument, {"files": 0, "seconds": 0, "nontrivial_days": 0})
        rec["files"] += 1
        rec["seconds"] += int(row["seconds"])
        if int(row["seconds"]) >= 3600:
            rec["nontrivial_days"] += 1
    return {
        "version": manifest["version"],
        "generated_at": manifest.get("generated_at"),
        "resolution": manifest.get("resolution"),
        "instruments": summary,
    }


def _source_live(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.startswith("live:")


def read_canonical_partition(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, usecols=CANONICAL_COLUMNS)
    raw["second"] = pd.to_datetime(raw["second"], utc=True)
    raw["minute"] = raw["second"].dt.floor("min")
    has_trade = raw["trade_count"] > 0
    has_quote = raw["quote_updates"] > 0
    has_depth = raw["depth_rows"] > 0
    raw["trade_open_valid"] = raw["trade_open"].where(has_trade)
    raw["trade_high_valid"] = raw["trade_high"].where(has_trade)
    raw["trade_low_valid"] = raw["trade_low"].where(has_trade)
    raw["trade_close_valid"] = raw["trade_close"].where(has_trade)
    raw["trade_second"] = has_trade.astype(np.int16)
    raw["quote_second"] = has_quote.astype(np.int16)
    raw["depth_second"] = has_depth.astype(np.int16)
    raw["trade_live"] = _source_live(raw["trade_source"]).astype(np.int16)
    raw["quote_live"] = _source_live(raw["quote_source"]).astype(np.int16)
    raw["depth_live"] = _source_live(raw["depth_source"]).astype(np.int16)
    raw["delta"] = raw["buy_volume"] - raw["sell_volume"]
    near_bid = raw[["bid_p0_volume", "bid_p1_volume", "bid_p2_volume"]].sum(axis=1)
    far_bid = raw[["bid_p7_volume", "bid_p8_volume", "bid_p9_volume"]].sum(axis=1)
    near_ask = raw[["ask_p0_volume", "ask_p1_volume", "ask_p2_volume"]].sum(axis=1)
    far_ask = raw[["ask_p7_volume", "ask_p8_volume", "ask_p9_volume"]].sum(axis=1)
    book_total = near_bid + far_bid + near_ask + far_ask
    raw["book_slope"] = ((near_bid - far_bid) - (near_ask - far_ask)) / (book_total + 1.0)

    grouped = raw.groupby("minute", sort=True).agg(
        rows=("second", "size"),
        trade_seconds=("trade_second", "sum"),
        quote_seconds=("quote_second", "sum"),
        depth_seconds=("depth_second", "sum"),
        trade_live_seconds=("trade_live", "sum"),
        quote_live_seconds=("quote_live", "sum"),
        depth_live_seconds=("depth_live", "sum"),
        open=("trade_open_valid", "first"),
        high=("trade_high_valid", "max"),
        low=("trade_low_valid", "min"),
        close=("trade_close_valid", "last"),
        volume=("trade_volume", "sum"),
        trades=("trade_count", "sum"),
        buy_volume=("buy_volume", "sum"),
        sell_volume=("sell_volume", "sum"),
        delta=("delta", "sum"),
        quote_updates=("quote_updates", "sum"),
        last_bid=("last_bid", "last"),
        last_ask=("last_ask", "last"),
        spread_mean=("last_spread", "mean"),
        spread_std=("last_spread", "std"),
        depth_rows=("depth_rows", "sum"),
        depth_bid_total=("last_depth_bid_total", "mean"),
        depth_ask_total=("last_depth_ask_total", "mean"),
        depth_imbalance=("last_depth_imbalance", "mean"),
        depth_imbalance_std=("last_depth_imbalance", "std"),
        book_slope=("book_slope", "mean"),
    )
    grouped.index.name = "bar_time"
    return grouped


def read_instrument_minutes(canonical_dir: Path, instrument: str) -> pd.DataFrame:
    pattern = f"canonical_{instrument.lower()}_*_1s.csv.gz"
    paths = sorted(canonical_dir.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no canonical partitions match {pattern}")
    frames = []
    for number, path in enumerate(paths, start=1):
        if int(partition_date(path).replace("-", "")) > 20260605:
            continue
        print(f"[{instrument}] reading {number}/{len(paths)} {path.name}", flush=True)
        frame = read_canonical_partition(path)
        frames.append(frame)
    minutes = pd.concat(frames).sort_index()
    minutes = minutes[~minutes.index.duplicated(keep="last")]
    minutes["quality"] = (
        (minutes["rows"] >= 55)
        & (minutes["trade_seconds"] >= 30)
        & (minutes["quote_seconds"] >= 50)
        & (minutes["depth_seconds"] >= 50)
        & minutes["open"].notna()
        & minutes["close"].notna()
    )
    minutes["trade_live_ratio"] = minutes["trade_live_seconds"] / minutes["trade_seconds"].clip(lower=1)
    minutes["quote_live_ratio"] = minutes["quote_live_seconds"] / minutes["quote_seconds"].clip(lower=1)
    minutes["depth_live_ratio"] = minutes["depth_live_seconds"] / minutes["depth_seconds"].clip(lower=1)
    return minutes


def cache_minutes(config: ResearchConfig, rebuild: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    cache_dir = config.out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = []
    for instrument in ("MNQ", "NQ"):
        path = cache_dir / f"{instrument.lower()}_minutes.csv.gz"
        if path.exists() and not rebuild:
            frame = pd.read_csv(path, index_col="bar_time", parse_dates=["bar_time"])
            frame.index = pd.to_datetime(frame.index, utc=True)
        else:
            frame = read_instrument_minutes(config.canonical_dir, instrument)
            frame.to_csv(path, compression="gzip", float_format="%.8f")
        output.append(frame)
    return output[0], output[1]


def trading_day_and_session(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    local = index.tz_convert(NEW_YORK)
    minute_of_day = local.hour * 60 + local.minute
    days = np.asarray(local.date, dtype=object)
    rolled = np.asarray(
        [value + timedelta(days=1) if minute >= 18 * 60 else value for value, minute in zip(days, minute_of_day)],
        dtype=object,
    )
    session = np.full(len(index), "overnight", dtype=object)
    session[(minute_of_day >= 570) & (minute_of_day < 660)] = "rth_open"
    session[(minute_of_day >= 660) & (minute_of_day < 930)] = "rth_mid"
    session[(minute_of_day >= 930) & (minute_of_day < 960)] = "rth_close"
    return pd.Series(rolled, index=index), pd.Series(session, index=index)


def segment_rolling(
    frame: pd.DataFrame,
    column: str,
    window: int,
    operation: str,
    min_periods: int | None = None,
) -> pd.Series:
    min_periods = min_periods if min_periods is not None else window
    grouped = frame.groupby("segment", sort=False)[column]
    if operation == "mean":
        return grouped.transform(lambda values: values.rolling(window, min_periods=min_periods).mean())
    if operation == "std":
        return grouped.transform(lambda values: values.rolling(window, min_periods=min_periods).std())
    if operation == "max":
        return grouped.transform(lambda values: values.rolling(window, min_periods=min_periods).max())
    if operation == "min":
        return grouped.transform(lambda values: values.rolling(window, min_periods=min_periods).min())
    if operation == "sum":
        return grouped.transform(lambda values: values.rolling(window, min_periods=min_periods).sum())
    raise ValueError(f"unknown rolling operation: {operation}")


def segment_shift(frame: pd.DataFrame, column: str, periods: int) -> pd.Series:
    return frame.groupby("segment", sort=False)[column].shift(periods)


def build_minute_features(mnq: pd.DataFrame, nq: pd.DataFrame) -> pd.DataFrame:
    frame = mnq.copy()
    frame["segment"] = frame.index.to_series().diff().ne(pd.Timedelta(minutes=1)).cumsum().to_numpy()
    frame["trading_day"], frame["session_bucket"] = trading_day_and_session(frame.index)
    frame["decision_time"] = frame.index + pd.Timedelta(minutes=1)
    local_decision = pd.DatetimeIndex(frame["decision_time"]).tz_convert(NEW_YORK)
    minute_of_day = local_decision.hour * 60 + local_decision.minute
    angle = 2.0 * np.pi * minute_of_day / 1440.0
    frame["minute_sin"] = np.sin(angle)
    frame["minute_cos"] = np.cos(angle)
    frame["is_rth"] = ((minute_of_day >= 570) & (minute_of_day < 960)).astype(float)
    frame["is_rth_open"] = ((minute_of_day >= 570) & (minute_of_day < 660)).astype(float)
    frame["is_rth_close"] = ((minute_of_day >= 930) & (minute_of_day < 960)).astype(float)

    prior_close = segment_shift(frame, "close", 1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prior_close).abs(),
            (frame["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["true_range"] = true_range
    frame["atr_14"] = segment_rolling(frame.assign(true_range=true_range), "true_range", 14, "mean")
    frame["atr_60"] = segment_rolling(frame.assign(true_range=true_range), "true_range", 60, "mean")
    for minutes in (1, 5, 15, 60):
        previous = segment_shift(frame, "close", minutes)
        frame[f"ret_{minutes}m"] = frame["close"] / previous - 1.0
    frame["return_1m_for_rv"] = frame["ret_1m"]
    frame["rv_15m_atr"] = (
        segment_rolling(frame, "return_1m_for_rv", 15, "std") * frame["close"] / frame["atr_14"]
    )
    frame["range_1m_atr"] = (frame["high"] - frame["low"]) / frame["atr_14"]

    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    pv = typical * frame["volume"]
    day_volume = frame.groupby("trading_day", sort=False)["volume"].cumsum()
    day_pv = pv.groupby(frame["trading_day"], sort=False).cumsum()
    frame["vwap"] = day_pv / day_volume.replace(0, np.nan)
    frame["dist_vwap_atr"] = (frame["close"] - frame["vwap"]) / frame["atr_14"]
    for window in (15, 60):
        recent_high = segment_rolling(frame, "high", window, "max")
        recent_low = segment_rolling(frame, "low", window, "min")
        frame[f"dist_high_{window}_atr"] = (frame["close"] - recent_high) / frame["atr_14"]
        frame[f"dist_low_{window}_atr"] = (frame["close"] - recent_low) / frame["atr_14"]

    frame["delta_pct"] = frame["delta"] / frame["volume"].clip(lower=1)
    for column, output_name in [
        ("volume", "volume_ratio_20"),
        ("trades", "trades_ratio_20"),
        ("quote_updates", "quote_ratio_20"),
        ("depth_rows", "depth_ratio_20"),
    ]:
        rolling = segment_rolling(frame, column, 20, "mean")
        frame[output_name] = frame[column] / rolling.replace(0, np.nan)
    frame["delta_abs"] = frame["delta"].abs()
    rolling_delta = segment_rolling(frame, "delta_abs", 20, "mean")
    frame["delta_ratio_20"] = frame["delta"] / rolling_delta.replace(0, np.nan)
    frame["spread_atr"] = frame["spread_mean"] / frame["atr_14"]
    frame["spread_vol_20"] = segment_rolling(frame, "spread_mean", 20, "std") / frame["atr_14"]
    frame["depth_imbalance_change"] = frame["depth_imbalance"] - segment_shift(frame, "depth_imbalance", 1)
    frame["depth_imbalance_persist_10"] = segment_rolling(frame, "depth_imbalance", 10, "mean")
    frame["quality_ratio_60"] = segment_rolling(
        frame.assign(quality_float=frame["quality"].astype(float)),
        "quality_float",
        60,
        "mean",
    )

    nq_features = nq.copy()
    nq_features["nq_segment"] = (
        nq_features.index.to_series().diff().ne(pd.Timedelta(minutes=1)).cumsum().to_numpy()
    )
    nq_features["nq_ret_1m"] = nq_features["close"] / nq_features.groupby("nq_segment")["close"].shift(1) - 1.0
    nq_features["nq_ret_5m"] = nq_features["close"] / nq_features.groupby("nq_segment")["close"].shift(5) - 1.0
    nq_features["nq_delta_pct"] = nq_features["delta"] / nq_features["volume"].clip(lower=1)
    nq_join = nq_features[["nq_ret_1m", "nq_ret_5m", "nq_delta_pct", "depth_imbalance", "quality"]].rename(
        columns={"depth_imbalance": "nq_depth_imbalance", "quality": "nq_quality"}
    )
    frame = frame.join(nq_join, how="left")
    frame["mnq_nq_div_1m"] = frame["ret_1m"] - frame["nq_ret_1m"]
    frame["decision_valid"] = (
        frame["quality"]
        & frame["nq_quality"].fillna(False)
        & (frame["quality_ratio_60"] >= 0.95)
        & frame["atr_14"].gt(0)
    )
    return frame


def is_formula_signal(row: pd.Series, direction: int) -> float:
    if direction > 0:
        matched = (
            row["low"] < row["vwap"]
            and row["close"] > row["vwap"]
            and row["delta_pct"] > 0.20
            and row["volume_ratio_20"] > 1.20
        )
    else:
        matched = (
            row["high"] > row["vwap"]
            and row["close"] < row["vwap"]
            and row["delta_pct"] < -0.20
            and row["volume_ratio_20"] > 1.20
        )
    return float(matched)


def label_direction(
    bars: pd.DataFrame,
    position: int,
    direction: int,
    config: ResearchConfig,
) -> dict | None:
    entry_pos = position + 1
    end_pos = entry_pos + config.horizon_minutes
    if end_pos > len(bars):
        return None
    expected_entry = bars.index[position] + pd.Timedelta(minutes=1)
    if bars.index[entry_pos] != expected_entry:
        return None
    future = bars.iloc[entry_pos:end_pos]
    if len(future) != config.horizon_minutes:
        return None
    if future.index[-1] - future.index[0] != pd.Timedelta(minutes=config.horizon_minutes - 1):
        return None
    if not bool(future["quality"].all()):
        return None
    signal = bars.iloc[position]
    entry = float(future.iloc[0]["open"])
    risk = max(float(signal["atr_14"]) * config.stop_atr, config.min_stop_points)
    stop = entry - direction * risk
    target = entry + direction * config.target_r * risk
    outcome = "timeout"
    exit_price = float(future.iloc[-1]["close"])
    exit_time = future.index[-1] + pd.Timedelta(minutes=1)
    exit_offset = len(future) - 1
    for offset, (bar_time, bar) in enumerate(future.iterrows()):
        hit_stop = float(bar["low"]) <= stop if direction > 0 else float(bar["high"]) >= stop
        hit_target = float(bar["high"]) >= target if direction > 0 else float(bar["low"]) <= target
        if hit_stop:
            outcome = "stop"
            exit_price = stop
            exit_time = bar_time + pd.Timedelta(minutes=1)
            exit_offset = offset
            break
        if hit_target:
            outcome = "target"
            exit_price = target
            exit_time = bar_time + pd.Timedelta(minutes=1)
            exit_offset = offset
            break
    trade_path = future.iloc[: exit_offset + 1]
    if direction > 0:
        mfe_r = (float(trade_path["high"].max()) - entry) / risk
        mae_r = (float(trade_path["low"].min()) - entry) / risk
    else:
        mfe_r = (entry - float(trade_path["low"].min())) / risk
        mae_r = (entry - float(trade_path["high"].max())) / risk
    gross_r = direction * (exit_price - entry) / risk
    gross_pnl = gross_r * risk * POINT_VALUE
    net_pnl = gross_pnl - config.fixed_cost_dollars
    return {
        "entry_time": future.index[0],
        "exit_time": exit_time,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "exit": exit_price,
        "outcome": outcome,
        "target_before_stop": int(outcome == "target"),
        "risk_points": risk,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "gross_r": gross_r,
        "net_r": net_pnl / (risk * POINT_VALUE),
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
    }


def build_directional_labels(
    features: pd.DataFrame,
    config: ResearchConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    local_decision = pd.DatetimeIndex(features["decision_time"]).tz_convert(NEW_YORK)
    decision_mask = (
        features["decision_valid"]
        & (local_decision.minute % config.decision_interval_minutes == 0)
        & (features["trading_day"].astype(str) >= "2026-04-01")
        & (features["trading_day"].astype(str) <= "2026-06-05")
    )
    decision_positions = np.flatnonzero(decision_mask.to_numpy())
    decision_rows = []
    directional_rows = []
    for position in decision_positions:
        row = features.iloc[position]
        base = {
            "bar_time": features.index[position],
            "decision_time": row["decision_time"],
            "trading_day": str(row["trading_day"]),
            "session_bucket": row["session_bucket"],
        }
        for name in [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trades",
            "delta",
            "vwap",
            "atr_14",
            "trade_live_ratio",
            "quote_live_ratio",
            "depth_live_ratio",
            "quality_ratio_60",
        ]:
            base[name] = row[name]
        for name in [
            "ret_1m",
            "ret_5m",
            "ret_15m",
            "ret_60m",
            "rv_15m_atr",
            "range_1m_atr",
            "dist_vwap_atr",
            "dist_high_15_atr",
            "dist_low_15_atr",
            "dist_high_60_atr",
            "dist_low_60_atr",
            "volume_ratio_20",
            "trades_ratio_20",
            "delta_pct",
            "delta_ratio_20",
            "spread_atr",
            "spread_vol_20",
            "quote_ratio_20",
            "depth_imbalance",
            "depth_imbalance_change",
            "depth_imbalance_persist_10",
            "depth_ratio_20",
            "book_slope",
            "minute_sin",
            "minute_cos",
            "is_rth",
            "is_rth_open",
            "is_rth_close",
            "nq_ret_1m",
            "nq_ret_5m",
            "mnq_nq_div_1m",
            "nq_delta_pct",
            "nq_depth_imbalance",
        ]:
            base[name] = row[name]
        decision_rows.append(base)
        for direction in (1, -1):
            label = label_direction(features, position, direction, config)
            if label is None:
                continue
            record = dict(base)
            record.update(label)
            record["formula_signal"] = is_formula_signal(row, direction)
            record["direction"] = float(direction)
            for name in [
                "ret_1m",
                "ret_5m",
                "ret_15m",
                "ret_60m",
                "dist_vwap_atr",
                "dist_high_15_atr",
                "dist_low_15_atr",
                "dist_high_60_atr",
                "dist_low_60_atr",
                "delta_pct",
                "delta_ratio_20",
                "depth_imbalance",
                "depth_imbalance_change",
                "depth_imbalance_persist_10",
                "book_slope",
                "nq_ret_1m",
                "nq_ret_5m",
                "mnq_nq_div_1m",
                "nq_delta_pct",
                "nq_depth_imbalance",
            ]:
                record[f"signed_{name}"] = direction * float(row[name])
            directional_rows.append(record)
    decisions = pd.DataFrame(decision_rows)
    labels = pd.DataFrame(directional_rows)
    labels["row_id"] = np.arange(len(labels), dtype=int)
    return decisions, labels


class Standardizer:
    def __init__(self) -> None:
        self.median: np.ndarray | None = None
        self.mean: np.ndarray | None = None
        self.std: np.ndarray | None = None

    def fit(self, values: np.ndarray) -> "Standardizer":
        self.median = np.nanmedian(values, axis=0)
        filled = np.where(np.isnan(values), self.median, values)
        self.mean = filled.mean(axis=0)
        self.std = filled.std(axis=0)
        self.std[self.std < 1e-9] = 1.0
        return self

    def transform(self, values: np.ndarray) -> np.ndarray:
        if self.median is None or self.mean is None or self.std is None:
            raise RuntimeError("standardizer is not fit")
        filled = np.where(np.isnan(values), self.median, values)
        return (filled - self.mean) / self.std


def sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-values))


class LogisticRegressionBaseline:
    def __init__(self, l2: float = 0.05, learning_rate: float = 0.04, iterations: int = 350):
        self.l2 = l2
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.weights: np.ndarray | None = None

    def fit(self, values: np.ndarray, labels: np.ndarray) -> "LogisticRegressionBaseline":
        design = np.column_stack([np.ones(len(values)), values])
        weights = np.zeros(design.shape[1], dtype=float)
        first = np.zeros_like(weights)
        second = np.zeros_like(weights)
        for iteration in range(1, self.iterations + 1):
            probability = sigmoid(design @ weights)
            gradient = design.T @ (probability - labels) / len(labels)
            gradient[1:] += self.l2 * weights[1:]
            first = 0.9 * first + 0.1 * gradient
            second = 0.999 * second + 0.001 * (gradient * gradient)
            first_hat = first / (1.0 - 0.9**iteration)
            second_hat = second / (1.0 - 0.999**iteration)
            weights -= self.learning_rate * first_hat / (np.sqrt(second_hat) + 1e-8)
        self.weights = weights
        return self

    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("logistic model is not fit")
        design = np.column_stack([np.ones(len(values)), values])
        return sigmoid(design @ self.weights)


class BoostedStumpsBaseline:
    def __init__(self, estimators: int = 60, learning_rate: float = 0.12):
        self.estimators = estimators
        self.learning_rate = learning_rate
        self.initial_logit = 0.0
        self.stumps: list[tuple[int, float, float, float]] = []

    def fit(self, values: np.ndarray, labels: np.ndarray) -> "BoostedStumpsBaseline":
        prevalence = float(np.clip(labels.mean(), 1e-4, 1.0 - 1e-4))
        self.initial_logit = math.log(prevalence / (1.0 - prevalence))
        raw = np.full(len(labels), self.initial_logit, dtype=float)
        thresholds = np.array([-1.5, -1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0, 1.5])
        self.stumps = []
        for _ in range(self.estimators):
            residual = labels - sigmoid(raw)
            best: tuple[float, int, float, float, float] | None = None
            for feature in range(values.shape[1]):
                column = values[:, feature]
                for threshold in thresholds:
                    left = column <= threshold
                    left_count = int(left.sum())
                    if left_count < 20 or len(column) - left_count < 20:
                        continue
                    left_value = float(residual[left].mean())
                    right_value = float(residual[~left].mean())
                    prediction = np.where(left, left_value, right_value)
                    error = float(np.mean((residual - prediction) ** 2))
                    if best is None or error < best[0]:
                        best = (error, feature, float(threshold), left_value, right_value)
            if best is None:
                break
            _, feature, threshold, left_value, right_value = best
            self.stumps.append((feature, threshold, left_value, right_value))
            raw += self.learning_rate * np.where(
                values[:, feature] <= threshold,
                left_value,
                right_value,
            )
        return self

    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        raw = np.full(len(values), self.initial_logit, dtype=float)
        for feature, threshold, left_value, right_value in self.stumps:
            raw += self.learning_rate * np.where(
                values[:, feature] <= threshold,
                left_value,
                right_value,
            )
        return sigmoid(raw)


class HistoricalAnalogBaseline:
    def __init__(self, neighbors: int = 25):
        self.neighbors = neighbors
        self.values: np.ndarray | None = None
        self.labels: np.ndarray | None = None
        self.row_ids: np.ndarray | None = None

    def fit(self, values: np.ndarray, labels: np.ndarray, row_ids: np.ndarray) -> "HistoricalAnalogBaseline":
        self.values = values
        self.labels = labels
        self.row_ids = row_ids
        return self

    def predict_proba(
        self,
        values: np.ndarray,
        return_neighbors: bool = False,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        if self.values is None or self.labels is None or self.row_ids is None:
            raise RuntimeError("analog model is not fit")
        k = min(self.neighbors, len(self.values))
        scores = np.empty(len(values), dtype=float)
        neighbor_ids = np.empty((len(values), k), dtype=int) if return_neighbors else None
        train_norm = np.sum(self.values * self.values, axis=1)
        for start in range(0, len(values), 256):
            query = values[start : start + 256]
            distance = (
                np.sum(query * query, axis=1)[:, None]
                + train_norm[None, :]
                - 2.0 * query @ self.values.T
            )
            nearest = np.argpartition(distance, k - 1, axis=1)[:, :k]
            nearest_distance = np.take_along_axis(distance, nearest, axis=1)
            order = np.argsort(nearest_distance, axis=1)
            nearest = np.take_along_axis(nearest, order, axis=1)
            nearest_distance = np.take_along_axis(nearest_distance, order, axis=1)
            weights = 1.0 / (np.sqrt(np.maximum(nearest_distance, 0.0)) + 0.25)
            neighbor_labels = self.labels[nearest]
            scores[start : start + len(query)] = (
                (weights * neighbor_labels).sum(axis=1) / weights.sum(axis=1)
            )
            if neighbor_ids is not None:
                neighbor_ids[start : start + len(query)] = self.row_ids[nearest]
        return scores, neighbor_ids


def date_slice(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame[(frame["trading_day"] >= start) & (frame["trading_day"] <= end)].copy()


def fit_and_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    config: ResearchConfig,
    include_neighbors: bool = False,
) -> tuple[dict[str, np.ndarray], np.ndarray | None]:
    if pd.to_datetime(train["exit_time"], utc=True).max() >= pd.to_datetime(test["decision_time"], utc=True).min():
        raise ValueError("purge violation: training labels overlap test decisions")
    all_scaler = Standardizer().fit(train[MODEL_FEATURES].to_numpy(dtype=float))
    train_all = all_scaler.transform(train[MODEL_FEATURES].to_numpy(dtype=float))
    test_all = all_scaler.transform(test[MODEL_FEATURES].to_numpy(dtype=float))
    labels = train["target_before_stop"].to_numpy(dtype=float)
    if SKLEARN_AVAILABLE:
        logistic = SklearnLogisticRegression(
            C=1.0,
            max_iter=2000,
            random_state=config.seed,
        ).fit(train_all, labels)
        boosted = HistGradientBoostingClassifier(
            learning_rate=0.06,
            max_iter=150,
            max_leaf_nodes=7,
            min_samples_leaf=30,
            l2_regularization=1.0,
            random_state=config.seed,
        ).fit(train_all, labels)
        logistic_scores = logistic.predict_proba(test_all)[:, 1]
        boosted_scores = boosted.predict_proba(test_all)[:, 1]
        boosted_name = "gradient_boosted_trees"
    else:
        logistic = LogisticRegressionBaseline().fit(train_all, labels)
        boosted = BoostedStumpsBaseline().fit(train_all, labels)
        logistic_scores = logistic.predict_proba(test_all)
        boosted_scores = boosted.predict_proba(test_all)
        boosted_name = "boosted_stumps_fallback"

    analog_scaler = Standardizer().fit(train[ANALOG_FEATURES].to_numpy(dtype=float))
    train_analog = analog_scaler.transform(train[ANALOG_FEATURES].to_numpy(dtype=float))
    test_analog = analog_scaler.transform(test[ANALOG_FEATURES].to_numpy(dtype=float))
    analog = HistoricalAnalogBaseline(config.analog_neighbors).fit(
        train_analog,
        labels,
        train["row_id"].to_numpy(dtype=int),
    )
    analog_scores, neighbor_ids = analog.predict_proba(test_analog, return_neighbors=include_neighbors)
    return {
        "analog": analog_scores,
        "logistic": logistic_scores,
        boosted_name: boosted_scores,
    }, neighbor_ids


def prediction_records(
    test: pd.DataFrame,
    scores: dict[str, np.ndarray],
    period: str,
    fold: str,
) -> pd.DataFrame:
    records = []
    keep = [
        "row_id",
        "decision_time",
        "entry_time",
        "exit_time",
        "trading_day",
        "session_bucket",
        "direction",
        "outcome",
        "target_before_stop",
        "risk_points",
        "gross_r",
        "net_r",
        "gross_pnl",
        "net_pnl",
        "mfe_r",
        "mae_r",
        "formula_signal",
    ]
    for model_name, model_scores in scores.items():
        frame = test[keep].copy()
        frame["model"] = model_name
        frame["score"] = model_scores
        frame["period"] = period
        frame["fold"] = fold
        records.append(frame)
    return pd.concat(records, ignore_index=True)


def select_nonoverlapping(predictions: pd.DataFrame, threshold: float) -> pd.DataFrame:
    eligible = predictions[predictions["score"] >= threshold].copy()
    if eligible.empty:
        return eligible
    eligible = eligible.sort_values(
        ["decision_time", "score", "direction"],
        ascending=[True, False, False],
    )
    eligible = eligible.drop_duplicates("decision_time", keep="first")
    selected = []
    next_free: pd.Timestamp | None = None
    for row in eligible.itertuples(index=False):
        decision_time = pd.Timestamp(row.decision_time)
        if next_free is not None and decision_time < next_free:
            continue
        selected.append(row)
        next_free = pd.Timestamp(row.exit_time)
    if not selected:
        return eligible.iloc[0:0]
    return pd.DataFrame(selected, columns=eligible.columns)


def max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def summarize_selected(selected: pd.DataFrame, model: str, period: str, threshold: float) -> dict:
    if selected.empty:
        return {
            "model": model,
            "period": period,
            "threshold": threshold,
            "trades": 0,
            "targets": 0,
            "win_rate": 0.0,
            "gross_r": 0.0,
            "net_r": 0.0,
            "net_pnl": 0.0,
            "max_drawdown": 0.0,
            "positive_days": 0,
            "negative_days": 0,
            "long_trades": 0,
            "short_trades": 0,
            "best_trade_share": 0.0,
        }
    ordered = selected.sort_values("decision_time")
    by_day = ordered.groupby("trading_day")["net_pnl"].sum()
    total_pnl = float(ordered["net_pnl"].sum())
    return {
        "model": model,
        "period": period,
        "threshold": threshold,
        "trades": len(ordered),
        "targets": int(ordered["target_before_stop"].sum()),
        "win_rate": float(ordered["target_before_stop"].mean()),
        "gross_r": float(ordered["gross_r"].sum()),
        "net_r": float(ordered["net_r"].sum()),
        "net_pnl": total_pnl,
        "max_drawdown": max_drawdown(ordered["net_pnl"]),
        "positive_days": int((by_day > 0).sum()),
        "negative_days": int((by_day < 0).sum()),
        "long_trades": int((ordered["direction"] > 0).sum()),
        "short_trades": int((ordered["direction"] < 0).sum()),
        "best_trade_share": float(ordered["net_pnl"].max() / total_pnl) if total_pnl > 0 else 0.0,
    }


def score_thresholds(predictions: pd.DataFrame) -> list[dict]:
    candidates = list(np.arange(0.30, 0.71, 0.05))
    candidates.extend(predictions["score"].quantile([0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95]).tolist())
    candidates = sorted(set(round(float(value), 6) for value in candidates if np.isfinite(value)))
    results = []
    for threshold in candidates:
        selected = select_nonoverlapping(predictions, threshold)
        if len(selected) < 10:
            continue
        summary = summarize_selected(selected, "threshold_search", "development_oof", threshold)
        results.append(summary)
    results.sort(key=lambda row: (row["net_pnl"], -row["max_drawdown"], row["trades"]), reverse=True)
    return results


def choose_threshold(predictions: pd.DataFrame) -> float:
    results = score_thresholds(predictions)
    if not results:
        return 1.10
    if float(results[0]["net_pnl"]) <= 0:
        return 1.10
    return float(results[0]["threshold"])


def calibration_rows(predictions: pd.DataFrame) -> list[dict]:
    rows = []
    for (period, model), group in predictions.groupby(["period", "model"], sort=True):
        scores = group["score"].clip(0.0, 1.0)
        actual = group["target_before_stop"].astype(float)
        brier = float(np.mean((scores - actual) ** 2))
        bins = pd.cut(scores, bins=np.linspace(0.0, 1.0, 6), include_lowest=True, duplicates="drop")
        for bucket, bucket_rows in group.groupby(bins, observed=True):
            rows.append(
                {
                    "period": period,
                    "model": model,
                    "bucket": str(bucket),
                    "count": len(bucket_rows),
                    "mean_score": float(bucket_rows["score"].mean()),
                    "actual_rate": float(bucket_rows["target_before_stop"].mean()),
                    "brier": brier,
                }
            )
    return rows


def random_control(
    candidates: pd.DataFrame,
    selected: pd.DataFrame,
    config: ResearchConfig,
    repetitions: int = 100,
) -> dict:
    if selected.empty:
        return {
            "mean_net_pnl": 0.0,
            "median_net_pnl": 0.0,
            "positive_rate": 0.0,
            "p95_net_pnl": 0.0,
        }
    rng = np.random.default_rng(config.seed)
    wanted = selected.groupby(["session_bucket", "direction"]).size()
    results = []
    for _ in range(repetitions):
        sampled = []
        for key, count in wanted.items():
            pool = candidates[
                (candidates["session_bucket"] == key[0])
                & (candidates["direction"] == key[1])
            ]
            if pool.empty:
                continue
            take = min(int(count), len(pool))
            sampled.append(pool.iloc[rng.choice(len(pool), size=take, replace=False)])
        if sampled:
            random_rows = pd.concat(sampled).sort_values("decision_time")
            results.append(float(random_rows["net_pnl"].sum()))
    values = np.asarray(results, dtype=float)
    return {
        "mean_net_pnl": float(values.mean()) if len(values) else 0.0,
        "median_net_pnl": float(np.median(values)) if len(values) else 0.0,
        "positive_rate": float((values > 0).mean()) if len(values) else 0.0,
        "p95_net_pnl": float(np.quantile(values, 0.95)) if len(values) else 0.0,
    }


def load_formula_baseline(path: Path, config: ResearchConfig) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = frame[(frame["timeframe"] == 1) & (frame["variant"] == FORMULA_VARIANT)].copy()
    frame["decision_time"] = pd.to_datetime(frame["signal_time"], utc=True)
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], utc=True)
    frame["exit_time"] = pd.to_datetime(frame["exit_time"], utc=True)
    frame["direction"] = frame["direction"].map({"long": 1.0, "short": -1.0})
    frame["gross_r"] = frame["r"].astype(float)
    frame["risk_points"] = frame["risk_points"].astype(float)
    frame["gross_pnl"] = frame["gross_r"] * frame["risk_points"] * POINT_VALUE
    frame["net_pnl"] = frame["gross_pnl"] - config.commission_round_turn
    frame["net_r"] = frame["net_pnl"] / (frame["risk_points"] * POINT_VALUE)
    frame["target_before_stop"] = (frame["outcome"] == "target").astype(int)
    frame["session_bucket"] = frame["rth_segment"].fillna(frame["session_rollup"])
    return frame


def formula_summary(formula: pd.DataFrame, start: str, end: str, period: str) -> dict:
    selected = date_slice(formula, start, end)
    return summarize_selected(selected, "formula_vwap_delta_rejection", period, float("nan"))


def build_formula_filter_rows(formula: pd.DataFrame, minute_features: pd.DataFrame) -> pd.DataFrame:
    context_columns = [
        "decision_time",
        "ret_1m",
        "ret_5m",
        "ret_15m",
        "ret_60m",
        "rv_15m_atr",
        "range_1m_atr",
        "dist_vwap_atr",
        "dist_high_15_atr",
        "dist_low_15_atr",
        "dist_high_60_atr",
        "dist_low_60_atr",
        "volume_ratio_20",
        "trades_ratio_20",
        "delta_pct",
        "delta_ratio_20",
        "spread_atr",
        "spread_vol_20",
        "quote_ratio_20",
        "depth_imbalance",
        "depth_imbalance_change",
        "depth_imbalance_persist_10",
        "depth_ratio_20",
        "book_slope",
        "minute_sin",
        "minute_cos",
        "is_rth",
        "is_rth_open",
        "is_rth_close",
        "nq_ret_1m",
        "nq_ret_5m",
        "mnq_nq_div_1m",
        "nq_delta_pct",
        "nq_depth_imbalance",
    ]
    context = minute_features[context_columns].drop_duplicates("decision_time")
    overlapping_context = [
        column
        for column in context_columns
        if column != "decision_time" and column in formula.columns
    ]
    rows = formula.drop(columns=overlapping_context).merge(
        context,
        on="decision_time",
        how="inner",
        validate="one_to_one",
    )
    if len(rows) != len(formula):
        raise ValueError(f"formula feature match incomplete: matched {len(rows)} of {len(formula)}")
    rows["actual_target_before_stop"] = rows["target_before_stop"]
    rows["target_before_stop"] = (rows["net_pnl"] > 0).astype(int)
    rows["formula_signal"] = 1.0
    signed_names = [
        "ret_1m",
        "ret_5m",
        "ret_15m",
        "ret_60m",
        "dist_vwap_atr",
        "dist_high_15_atr",
        "dist_low_15_atr",
        "dist_high_60_atr",
        "dist_low_60_atr",
        "delta_pct",
        "delta_ratio_20",
        "depth_imbalance",
        "depth_imbalance_change",
        "depth_imbalance_persist_10",
        "book_slope",
        "nq_ret_1m",
        "nq_ret_5m",
        "mnq_nq_div_1m",
        "nq_delta_pct",
        "nq_depth_imbalance",
    ]
    for name in signed_names:
        rows[f"signed_{name}"] = rows["direction"] * rows[name]
    rows["row_id"] = np.arange(1_000_000, 1_000_000 + len(rows), dtype=int)
    return rows


def score_filter_thresholds(predictions: pd.DataFrame) -> list[dict]:
    candidates = list(np.arange(0.30, 0.71, 0.05))
    candidates.extend(predictions["score"].quantile([0.40, 0.50, 0.60, 0.70, 0.80]).tolist())
    candidates = sorted(set(round(float(value), 6) for value in candidates if np.isfinite(value)))
    results = []
    for threshold in candidates:
        selected = predictions[predictions["score"] >= threshold].copy()
        if len(selected) < 10:
            continue
        results.append(
            {
                "threshold": threshold,
                "trades": len(selected),
                "net_pnl": float(selected["net_pnl"].sum()),
                "max_drawdown": max_drawdown(selected.sort_values("decision_time")["net_pnl"]),
            }
        )
    results.sort(key=lambda row: (row["net_pnl"], -row["max_drawdown"], row["trades"]), reverse=True)
    return results


def choose_filter_threshold(predictions: pd.DataFrame) -> tuple[float, dict]:
    baseline_net = float(predictions["net_pnl"].sum())
    results = score_filter_thresholds(predictions)
    if not results or float(results[0]["net_pnl"]) <= baseline_net:
        return 0.0, {
            "best_threshold": results[0]["threshold"] if results else 0.0,
            "best_trades": results[0]["trades"] if results else len(predictions),
            "best_net_pnl": results[0]["net_pnl"] if results else baseline_net,
            "best_max_drawdown": results[0]["max_drawdown"] if results else max_drawdown(predictions["net_pnl"]),
            "baseline_net_pnl": baseline_net,
            "frozen_action": "keep_all",
        }
    return float(results[0]["threshold"]), {
        "best_threshold": results[0]["threshold"],
        "best_trades": results[0]["trades"],
        "best_net_pnl": results[0]["net_pnl"],
        "best_max_drawdown": results[0]["max_drawdown"],
        "baseline_net_pnl": baseline_net,
        "frozen_action": "filter",
    }


def summarize_filter(
    predictions: pd.DataFrame,
    model: str,
    period: str,
    threshold: float,
) -> tuple[dict, pd.DataFrame]:
    selected = predictions[predictions["score"] >= threshold].copy()
    baseline_net = float(predictions["net_pnl"].sum())
    summary = {
        "model": model,
        "period": period,
        "threshold": threshold,
        "action": "filter" if threshold > 0 else "keep_all",
        "baseline_trades": len(predictions),
        "kept_trades": len(selected),
        "keep_pct": float(len(selected) / len(predictions)) if len(predictions) else 0.0,
        "profitable_rate": float(selected["target_before_stop"].mean()) if len(selected) else 0.0,
        "baseline_net_pnl": baseline_net,
        "filtered_net_pnl": float(selected["net_pnl"].sum()),
        "delta_net_pnl": float(selected["net_pnl"].sum()) - baseline_net,
        "filtered_max_drawdown": max_drawdown(selected.sort_values("decision_time")["net_pnl"]),
    }
    selected["filter_model"] = model
    selected["filter_period"] = period
    selected["filter_threshold"] = threshold
    return summary, selected


def run_formula_filter_research(
    formula_rows: pd.DataFrame,
    config: ResearchConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    predictions = []
    for fold_name, train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS:
        train = date_slice(formula_rows, train_start, train_end)
        test = date_slice(formula_rows, test_start, test_end)
        scores, _ = fit_and_predict(train, test, config)
        predictions.append(prediction_records(test, scores, "development_oof", fold_name))
    development = pd.concat(predictions, ignore_index=True)
    thresholds = {}
    diagnostics = []
    for model, group in development.groupby("model", sort=True):
        threshold, diagnostic = choose_filter_threshold(group)
        thresholds[model] = threshold
        diagnostics.append({"model": model, "frozen_threshold": threshold, **diagnostic})

    validation_train = date_slice(formula_rows, "2026-04-01", "2026-05-15")
    validation_test = date_slice(formula_rows, "2026-05-18", "2026-05-22")
    validation_scores, _ = fit_and_predict(validation_train, validation_test, config)
    validation = prediction_records(validation_test, validation_scores, "validation", "validation")

    final_train = date_slice(formula_rows, "2026-04-01", "2026-05-22")
    final_test = date_slice(formula_rows, "2026-05-25", "2026-06-05")
    final_scores, _ = fit_and_predict(final_train, final_test, config)
    final = prediction_records(final_test, final_scores, "final_test", "final_test")
    all_predictions = pd.concat([development, validation, final], ignore_index=True)

    summaries = []
    selected_frames = []
    for (period, model), group in all_predictions.groupby(["period", "model"], sort=True):
        summary, selected = summarize_filter(group, model, period, thresholds[model])
        summaries.append(summary)
        selected_frames.append(selected)
    return (
        all_predictions,
        pd.DataFrame(summaries),
        pd.DataFrame(diagnostics),
        pd.concat(selected_frames, ignore_index=True),
    )


def build_performance_breakdowns(
    selected: pd.DataFrame,
    formula: pd.DataFrame,
    minute_features: pd.DataFrame,
) -> pd.DataFrame:
    context = minute_features[["decision_time", "rv_15m_atr"]].drop_duplicates("decision_time")
    development_context = minute_features[
        minute_features["trading_day"].astype(str) <= "2026-05-15"
    ]
    low_cut, high_cut = development_context["rv_15m_atr"].quantile([0.33, 0.67]).tolist()

    frames = []
    if not selected.empty:
        model_rows = selected.copy()
        model_rows["source_model"] = model_rows["model"]
        frames.append(model_rows)
    for period, start, end in [
        ("development", "2026-04-01", "2026-05-15"),
        ("validation", "2026-05-18", "2026-05-22"),
        ("final_test", "2026-05-25", "2026-06-05"),
    ]:
        rows = date_slice(formula, start, end)
        rows["period"] = period
        rows["source_model"] = "formula_vwap_delta_rejection"
        frames.append(rows)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.merge(context, on="decision_time", how="left")
    combined["month"] = pd.to_datetime(combined["decision_time"], utc=True).dt.strftime("%Y-%m")
    combined["direction_label"] = np.where(combined["direction"] > 0, "long", "short")
    combined["volatility_regime"] = np.select(
        [
            combined["rv_15m_atr"] <= low_cut,
            combined["rv_15m_atr"] >= high_cut,
        ],
        ["low", "high"],
        default="mid",
    )
    rows = []
    for dimension, column in [
        ("month", "month"),
        ("session", "session_bucket"),
        ("direction", "direction_label"),
        ("volatility_regime", "volatility_regime"),
    ]:
        grouped = combined.groupby(["period", "source_model", column], dropna=False, sort=True)
        for (period, model, value), group in grouped:
            rows.append(
                {
                    "period": period,
                    "model": model,
                    "dimension": dimension,
                    "value": value,
                    "trades": len(group),
                    "target_rate": float(group["target_before_stop"].mean()),
                    "gross_r": float(group["gross_r"].sum()),
                    "net_r": float(group["net_r"].sum()),
                    "net_pnl": float(group["net_pnl"].sum()),
                    "max_drawdown": max_drawdown(group.sort_values("decision_time")["net_pnl"]),
                }
            )
    return pd.DataFrame(rows)


def build_leakage_audit(
    labels: pd.DataFrame,
    decisions: pd.DataFrame,
    selected: pd.DataFrame,
    analog_neighbors: pd.DataFrame,
) -> dict:
    split_checks = []
    for fold_name, train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS + [
        ("validation", "2026-04-01", "2026-05-15", "2026-05-18", "2026-05-22"),
        ("final_test", "2026-04-01", "2026-05-22", "2026-05-25", "2026-06-05"),
    ]:
        train = date_slice(labels, train_start, train_end)
        test = date_slice(labels, test_start, test_end)
        train_exit_max = pd.to_datetime(train["exit_time"], utc=True).max()
        test_decision_min = pd.to_datetime(test["decision_time"], utc=True).min()
        split_checks.append(
            {
                "name": fold_name,
                "train_exit_max": train_exit_max.isoformat(),
                "test_decision_min": test_decision_min.isoformat(),
                "purged": bool(train_exit_max < test_decision_min),
            }
        )
    overlap_violations = 0
    for _, group in selected.groupby(["period", "model"], sort=False):
        ordered = group.sort_values("decision_time")
        previous_exit = pd.to_datetime(ordered["exit_time"], utc=True).shift(1)
        decisions_time = pd.to_datetime(ordered["decision_time"], utc=True)
        overlap_violations += int((decisions_time < previous_exit).sum())
    neighbor_future = int(
        (
            pd.to_datetime(analog_neighbors["neighbor_decision_time"], utc=True)
            >= pd.to_datetime(analog_neighbors["query_decision_time"], utc=True)
        ).sum()
    )
    neighbor_same_day = int(
        (
            analog_neighbors["neighbor_trading_day"].astype(str)
            == pd.to_datetime(analog_neighbors["query_decision_time"], utc=True).dt.date.astype(str)
        ).sum()
    )
    checks = {
        "canonical_version_requirement": "version >= 3, enforced before reading",
        "feature_timing_violations": int(
            (
                pd.to_datetime(decisions["bar_time"], utc=True)
                >= pd.to_datetime(decisions["decision_time"], utc=True)
            ).sum()
        ),
        "entry_before_decision_violations": int(
            (
                pd.to_datetime(labels["entry_time"], utc=True)
                < pd.to_datetime(labels["decision_time"], utc=True)
            ).sum()
        ),
        "selected_trade_overlap_violations": overlap_violations,
        "analog_future_neighbor_violations": neighbor_future,
        "analog_same_day_neighbor_violations": neighbor_same_day,
        "split_checks": split_checks,
        "scalers_fit_on_training_only": True,
        "thresholds_selected_from_development_oof_only": True,
        "final_test_thresholds_frozen": True,
    }
    checks["passed"] = bool(
        checks["feature_timing_violations"] == 0
        and checks["entry_before_decision_violations"] == 0
        and checks["selected_trade_overlap_violations"] == 0
        and checks["analog_future_neighbor_violations"] == 0
        and checks["analog_same_day_neighbor_violations"] == 0
        and all(row["purged"] for row in split_checks)
    )
    return checks


def write_analog_neighbors(
    final_test: pd.DataFrame,
    final_predictions: pd.DataFrame,
    neighbor_ids: np.ndarray,
    labels_by_id: pd.DataFrame,
    threshold: float,
    output_path: Path,
) -> None:
    analog_predictions = final_predictions[final_predictions["model"] == "analog"].copy()
    analog_predictions["test_offset"] = np.arange(len(analog_predictions), dtype=int)
    selected = select_nonoverlapping(analog_predictions, threshold)
    proposed_trade = True
    if selected.empty:
        selected = analog_predictions.sort_values("score", ascending=False).head(10).copy()
        proposed_trade = False
    records = []
    lookup = labels_by_id.set_index("row_id")
    for selected_row in selected.itertuples(index=False):
        test_offset = int(selected_row.test_offset)
        for rank, neighbor_id in enumerate(neighbor_ids[test_offset][:5], start=1):
            neighbor = lookup.loc[int(neighbor_id)]
            records.append(
                {
                    "query_row_id": selected_row.row_id,
                    "query_decision_time": selected_row.decision_time,
                    "query_direction": selected_row.direction,
                    "query_score": selected_row.score,
                    "proposed_trade": proposed_trade,
                    "neighbor_rank": rank,
                    "neighbor_row_id": int(neighbor_id),
                    "neighbor_decision_time": neighbor["decision_time"],
                    "neighbor_trading_day": neighbor["trading_day"],
                    "neighbor_direction": neighbor["direction"],
                    "neighbor_outcome": neighbor["outcome"],
                    "neighbor_target_before_stop": neighbor["target_before_stop"],
                    "neighbor_net_pnl": neighbor["net_pnl"],
                }
            )
    pd.DataFrame(records).to_csv(output_path, index=False, float_format="%.8f")


def verdict_markdown(
    inventory: dict,
    summaries: pd.DataFrame,
    threshold_diagnostics: pd.DataFrame,
    formula_filter_summary: pd.DataFrame,
    formula_filter_diagnostics: pd.DataFrame,
    random_rows: list[dict],
    calibration: pd.DataFrame,
    config: ResearchConfig,
) -> str:
    final = summaries[summaries["period"] == "final_test"].sort_values("net_pnl", ascending=False)
    validation = summaries[summaries["period"] == "validation"].set_index("model")
    lines = [
        "# Pattern / ML Research Verdict",
        "",
        "Research-only first pass generated from canonical format version "
        f"{inventory['version']}. No broker connection or order submission was used.",
        "",
        "## Fixed Design",
        "",
        f"- Decisions: every {config.decision_interval_minutes} minutes from trailing one-minute features.",
        f"- Entry: next one-minute bar open; horizon: {config.horizon_minutes} minutes.",
        f"- Outcome: +{config.target_r:.0f}R target before -1R stop; same-bar ties are stops.",
        f"- Costs: ${config.commission_round_turn:.2f} commission plus "
        f"{config.slippage_ticks_per_side:g} tick per side (${config.fixed_cost_dollars:.2f} total fixed cost).",
        "- Development thresholds: chosen only from anchored walk-forward out-of-fold predictions.",
        "- Final test: May 25 through June 5, untouched until thresholds were frozen.",
        "",
        "## Final Test",
        "",
        "| Model | Frozen threshold | Trades | Target rate | Net PnL | Max DD | Days + / - | Best trade share |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in final.itertuples(index=False):
        threshold = "" if pd.isna(row.threshold) else f"{row.threshold:.3f}"
        lines.append(
            f"| `{row.model}` | {threshold} | {row.trades} | {row.win_rate:.1%} | "
            f"${row.net_pnl:+.2f} | ${row.max_drawdown:.2f} | "
            f"{row.positive_days} / {row.negative_days} | {row.best_trade_share:.1%} |"
        )
    lines.extend(
        [
            "",
            "## ML Filter Of Formula Candidate",
            "",
            "Filters are trained only on exact historical `vwap_delta_rejection` trades. "
            "A filter is frozen only if it improves total development walk-forward net PnL over keeping every formula trade.",
            "",
            "| Model | Development action | Best development delta | Validation delta | Final delta | Final kept |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    validation_filters = formula_filter_summary[
        formula_filter_summary["period"] == "validation"
    ].set_index("model")
    final_filters = formula_filter_summary[
        formula_filter_summary["period"] == "final_test"
    ].set_index("model")
    for row in formula_filter_diagnostics.sort_values("best_net_pnl", ascending=False).itertuples(index=False):
        validation_row = validation_filters.loc[row.model]
        final_row = final_filters.loc[row.model]
        lines.append(
            f"| `{row.model}` | {row.frozen_action} | "
            f"${row.best_net_pnl - row.baseline_net_pnl:+.2f} | "
            f"${validation_row.delta_net_pnl:+.2f} | ${final_row.delta_net_pnl:+.2f} | "
            f"{int(final_row.kept_trades)}/{int(final_row.baseline_trades)} |"
        )
    lines.extend(
        [
            "",
            "## Development Threshold Selection",
            "",
            "| Model | Best tested threshold | Trades | Net PnL | Max DD | Frozen action |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in threshold_diagnostics.sort_values("best_net_pnl", ascending=False).itertuples(index=False):
        lines.append(
            f"| `{row.model}` | {row.best_threshold:.3f} | {row.best_trades} | "
            f"${row.best_net_pnl:+.2f} | ${row.best_max_drawdown:.2f} | {row.frozen_action} |"
        )
    lines.extend(
        [
            "",
            "## Validation Check",
            "",
            "| Model | Trades | Net PnL | Max DD |",
            "|---|---:|---:|---:|",
        ]
    )
    for model, row in validation.sort_values("net_pnl", ascending=False).iterrows():
        lines.append(f"| `{model}` | {int(row.trades)} | ${row.net_pnl:+.2f} | ${row.max_drawdown:.2f} |")
    lines.extend(
        [
            "",
            "## Random Controls",
            "",
            "Random entries match each model's final-test direction and session-bucket counts over 100 deterministic repetitions.",
            "",
            "| Model | Random mean | Random median | Positive repetitions | Random 95th percentile |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in random_rows:
        lines.append(
            f"| `{row['model']}` | ${row['mean_net_pnl']:+.2f} | ${row['median_net_pnl']:+.2f} | "
            f"{row['positive_rate']:.1%} | ${row['p95_net_pnl']:+.2f} |"
        )
    lines.extend(
        [
            "",
            "## Calibration",
            "",
            "| Period | Model | Brier score |",
            "|---|---|---:|",
        ]
    )
    brier = calibration.groupby(["period", "model"], as_index=False)["brier"].first()
    for row in brier.itertuples(index=False):
        lines.append(f"| {row.period} | `{row.model}` | {row.brier:.4f} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is a prototype/rejection dataset, not proof of a durable edge. Two months of one contract, "
            "one expiry, and second-level event ordering limitations remain material.",
            "",
        ]
    )
    ml_final = final[
        final["model"].isin(
            ["analog", "logistic", "gradient_boosted_trees", "boosted_stumps_fallback"]
        )
    ]
    if ml_final.empty or float(ml_final["net_pnl"].max()) <= 0:
        lines.append(
            "**Verdict: reject these first independent ML entry baselines for promotion.** "
            "None produced positive net final-test PnL after frozen selection and realistic fixed costs."
        )
    else:
        best = ml_final.iloc[0]
        validation_row = validation.loc[best["model"]] if best["model"] in validation.index else None
        if validation_row is None or float(validation_row["net_pnl"]) <= 0:
            lines.append(
                f"**Verdict: do not promote `{best['model']}`.** It was positive in the final test but "
                "failed the preceding validation block, so stability is not credible."
            )
        else:
            lines.append(
                f"**Verdict: `{best['model']}` merits another research pass, not promotion.** It was positive "
                "in validation and final test, but requires broader history, sensitivity tests, and forward paper validation."
            )
    filter_final = formula_filter_summary[formula_filter_summary["period"] == "final_test"]
    if filter_final.empty or float(filter_final["delta_net_pnl"].max()) <= 0:
        lines.append(
            "\n**Formula-filter verdict: no tested ML filter adds value beyond keeping all formula signals.**"
        )
    else:
        best_filter = filter_final.sort_values("delta_net_pnl", ascending=False).iloc[0]
        lines.append(
            f"\n**Formula-filter verdict: `{best_filter['model']}` improved the frozen final subset by "
            f"${best_filter['delta_net_pnl']:+.2f}, but remains research-only pending broader history.**"
        )
    lines.extend(
        [
            "",
            "The exact existing `vwap_delta_rejection` formula rows are included as a contextual baseline. "
            "They use the existing analyzer's trade timing and can overlap, so they are not mechanically identical "
            "to the non-overlapping model selections.",
            "",
            "See `config.json`, `model_summary.csv`, `calibration.csv`, `selected_trades.csv`, and "
            "`analog_neighbors.csv`, `performance_breakdowns.csv`, and `leakage_audit.json` for the reproducible audit trail.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(config: ResearchConfig, rebuild_cache: bool = False) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    inventory = verify_manifest(config.canonical_dir)
    (config.out_dir / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    config_json = {
        **{key: str(value) if isinstance(value, Path) else value for key, value in config.__dict__.items()},
        "fixed_cost_dollars": config.fixed_cost_dollars,
        "model_backend": "scikit-learn" if SKLEARN_AVAILABLE else "self-contained fallback",
        "model_features": MODEL_FEATURES,
        "analog_features": ANALOG_FEATURES,
        "walk_forward_folds": WALK_FORWARD_FOLDS,
        "validation": ["2026-05-18", "2026-05-22"],
        "final_test": ["2026-05-25", "2026-06-05"],
    }
    (config.out_dir / "config.json").write_text(json.dumps(config_json, indent=2) + "\n")

    mnq, nq = cache_minutes(config, rebuild_cache)
    print("building trailing-only minute features", flush=True)
    minute_features = build_minute_features(mnq, nq)
    feature_export = minute_features.reset_index()
    feature_export.to_csv(
        config.out_dir / "minute_features.csv.gz",
        index=False,
        compression="gzip",
        float_format="%.8f",
    )
    print("building deterministic directional labels", flush=True)
    decisions, labels = build_directional_labels(minute_features, config)
    decisions.to_csv(
        config.out_dir / "decision_features_5m.csv.gz",
        index=False,
        compression="gzip",
        float_format="%.8f",
    )
    labels.to_csv(
        config.out_dir / "directional_labels.csv.gz",
        index=False,
        compression="gzip",
        float_format="%.8f",
    )

    predictions = []
    for fold_name, train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS:
        print(f"running {fold_name}: train through {train_end}, test {test_start}..{test_end}", flush=True)
        train = date_slice(labels, train_start, train_end)
        test = date_slice(labels, test_start, test_end)
        scores, _ = fit_and_predict(train, test, config)
        predictions.append(prediction_records(test, scores, "development_oof", fold_name))
    development = pd.concat(predictions, ignore_index=True)
    thresholds = {
        model: choose_threshold(group)
        for model, group in development.groupby("model", sort=True)
    }
    threshold_diagnostic_rows = []
    for model, group in development.groupby("model", sort=True):
        scored = score_thresholds(group)
        if scored:
            best = scored[0]
            threshold_diagnostic_rows.append(
                {
                    "model": model,
                    "best_threshold": best["threshold"],
                    "best_trades": best["trades"],
                    "best_net_pnl": best["net_pnl"],
                    "best_max_drawdown": best["max_drawdown"],
                    "frozen_threshold": thresholds[model],
                    "frozen_action": "trade" if thresholds[model] <= 1.0 else "no_trade",
                }
            )
    threshold_diagnostics = pd.DataFrame(threshold_diagnostic_rows)
    threshold_diagnostics.to_csv(
        config.out_dir / "threshold_selection.csv",
        index=False,
        float_format="%.8f",
    )

    print("running frozen-threshold validation", flush=True)
    validation_train = date_slice(labels, "2026-04-01", "2026-05-15")
    validation_test = date_slice(labels, "2026-05-18", "2026-05-22")
    validation_scores, _ = fit_and_predict(validation_train, validation_test, config)
    validation_predictions = prediction_records(
        validation_test,
        validation_scores,
        "validation",
        "validation",
    )

    print("running untouched final test", flush=True)
    final_train = date_slice(labels, "2026-04-01", "2026-05-22")
    final_test = date_slice(labels, "2026-05-25", "2026-06-05")
    final_scores, analog_neighbor_ids = fit_and_predict(
        final_train,
        final_test,
        config,
        include_neighbors=True,
    )
    final_predictions = prediction_records(final_test, final_scores, "final_test", "final_test")
    all_predictions = pd.concat([development, validation_predictions, final_predictions], ignore_index=True)
    all_predictions.to_csv(
        config.out_dir / "model_predictions.csv.gz",
        index=False,
        compression="gzip",
        float_format="%.8f",
    )

    selected_frames = []
    summaries = []
    random_rows = []
    for period, period_predictions in all_predictions.groupby("period", sort=False):
        for model, model_predictions in period_predictions.groupby("model", sort=True):
            threshold = thresholds[model]
            selected = select_nonoverlapping(model_predictions, threshold)
            selected["threshold"] = threshold
            selected_frames.append(selected)
            summaries.append(summarize_selected(selected, model, period, threshold))
            if period == "final_test":
                random_row = random_control(
                    final_test,
                    selected,
                    config,
                )
                random_row["model"] = model
                random_rows.append(random_row)

    formula = load_formula_baseline(config.baseline_trades, config)
    formula_filter_rows = build_formula_filter_rows(formula, minute_features)
    (
        formula_filter_predictions,
        formula_filter_summary,
        formula_filter_diagnostics,
        formula_filter_selected,
    ) = run_formula_filter_research(formula_filter_rows, config)
    formula_filter_predictions.to_csv(
        config.out_dir / "formula_filter_predictions.csv.gz",
        index=False,
        compression="gzip",
        float_format="%.8f",
    )
    formula_filter_summary.to_csv(
        config.out_dir / "formula_filter_summary.csv",
        index=False,
        float_format="%.8f",
    )
    formula_filter_diagnostics.to_csv(
        config.out_dir / "formula_filter_threshold_selection.csv",
        index=False,
        float_format="%.8f",
    )
    formula_filter_selected.to_csv(
        config.out_dir / "formula_filter_selected_trades.csv",
        index=False,
        float_format="%.8f",
    )
    summaries.append(formula_summary(formula, "2026-04-01", "2026-05-15", "development"))
    summaries.append(formula_summary(formula, "2026-05-18", "2026-05-22", "validation"))
    summaries.append(formula_summary(formula, "2026-05-25", "2026-06-05", "final_test"))
    selected = pd.concat(selected_frames, ignore_index=True)
    selected.to_csv(config.out_dir / "selected_trades.csv", index=False, float_format="%.8f")
    summary_frame = pd.DataFrame(summaries)
    summary_frame.to_csv(config.out_dir / "model_summary.csv", index=False, float_format="%.8f")
    calibration = pd.DataFrame(calibration_rows(all_predictions))
    calibration.to_csv(config.out_dir / "calibration.csv", index=False, float_format="%.8f")
    pd.DataFrame(random_rows).to_csv(config.out_dir / "random_controls.csv", index=False, float_format="%.8f")
    if analog_neighbor_ids is None:
        raise RuntimeError("final analog neighbor ids were not produced")
    write_analog_neighbors(
        final_test,
        final_predictions,
        analog_neighbor_ids,
        labels,
        thresholds["analog"],
        config.out_dir / "analog_neighbors.csv",
    )
    analog_neighbors = pd.read_csv(config.out_dir / "analog_neighbors.csv")
    breakdowns = build_performance_breakdowns(selected, formula, minute_features)
    breakdowns.to_csv(
        config.out_dir / "performance_breakdowns.csv",
        index=False,
        float_format="%.8f",
    )
    leakage_audit = build_leakage_audit(labels, decisions, selected, analog_neighbors)
    (config.out_dir / "leakage_audit.json").write_text(json.dumps(leakage_audit, indent=2) + "\n")
    (config.out_dir / "VERDICT.md").write_text(
        verdict_markdown(
            inventory,
            summary_frame,
            threshold_diagnostics,
            formula_filter_summary,
            formula_filter_diagnostics,
            random_rows,
            calibration,
            config,
        )
    )
    print(f"wrote research outputs to {config.out_dir}", flush=True)


def main() -> int:
    args = parse_args()
    config = ResearchConfig(
        canonical_dir=args.canonical_dir,
        baseline_trades=args.baseline_trades,
        out_dir=args.out,
        decision_interval_minutes=args.decision_interval_minutes,
        horizon_minutes=args.horizon_minutes,
        analog_neighbors=args.analog_neighbors,
    )
    run(config, rebuild_cache=args.rebuild_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
