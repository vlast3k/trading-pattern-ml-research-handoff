#!/usr/bin/env python3
"""Convert Databento parent-symbol trades into daily canonical 1-second partitions."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

import databento as db
import pandas as pd


OUTRIGHT = re.compile(r"^MNQ[HMUZ]\d$")
HEADER = [
    "second", "instrument", "trade_source", "quote_source", "depth_source",
    "trade_count", "trade_volume", "buy_volume", "sell_volume", "unknown_volume",
    "trade_open", "trade_high", "trade_low", "trade_close", "quote_updates",
    "bid_updates", "ask_updates", "last_bid", "last_ask", "last_bid_size",
    "last_ask_size", "min_spread", "max_spread", "last_spread", "depth_rows",
    "depth_snapshots", "last_depth_bid_total", "last_depth_ask_total",
    "last_depth_imbalance", "min_depth_imbalance", "max_depth_imbalance",
    "avg_depth_imbalance",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("data/databento_2025q1_replication/mnq_trades_2025q1")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/canonical_databento_mnq_2025q1")
    )
    parser.add_argument("--chunk-records", type=int, default=1_000_000)
    return parser.parse_args()


def frames(path: Path, count: int):
    yield from db.DBNStore.from_file(path).to_df(count=count)


def clean(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame[frame["symbol"].astype(str).str.match(OUTRIGHT)].copy()
    if frame.empty:
        return frame
    frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True)
    frame["day"] = frame["ts_event"].dt.strftime("%Y%m%d")
    return frame


def select_dominant(files: list[Path], count: int) -> dict[str, str]:
    volumes: dict[tuple[str, str], int] = defaultdict(int)
    for path in files:
        for frame in frames(path, count):
            frame = clean(frame)
            for row in frame.groupby(["day", "symbol"], observed=True)["size"].sum().items():
                volumes[row[0]] += int(row[1])
    days: dict[str, tuple[str, int]] = {}
    for (day, symbol), volume in volumes.items():
        if day not in days or volume > days[day][1]:
            days[day] = (symbol, volume)
    return {day: item[0] for day, item in sorted(days.items())}


def empty_second() -> dict[str, object]:
    return {
        "trade_count": 0, "trade_volume": 0, "buy_volume": 0, "sell_volume": 0,
        "unknown_volume": 0, "trade_open": None, "trade_high": None,
        "trade_low": None, "trade_close": None,
    }


def add_trade(item: dict[str, object], price: float, size: int, side: str) -> None:
    item["trade_count"] += 1
    item["trade_volume"] += size
    if side == "B":
        item["buy_volume"] += size
    elif side == "A":
        item["sell_volume"] += size
    else:
        item["unknown_volume"] += size
    if item["trade_open"] is None:
        item["trade_open"] = price
        item["trade_high"] = price
        item["trade_low"] = price
    item["trade_high"] = max(float(item["trade_high"]), price)
    item["trade_low"] = min(float(item["trade_low"]), price)
    item["trade_close"] = price


def write_day(out: Path, day: str, seconds: dict[pd.Timestamp, dict[str, object]]) -> Path:
    path = out / f"canonical_mnq_databento_{day}_1s.csv.gz"
    with gzip.open(path, "wt", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        for second, item in sorted(seconds.items()):
            row = {name: 0 for name in HEADER}
            row.update(item)
            row.update(
                {
                    "second": second.isoformat().replace("+00:00", "Z"),
                    "instrument": "MNQ DATABENTO",
                    "trade_source": "databento_trades",
                    "quote_source": "none",
                    "depth_source": "none",
                }
            )
            writer.writerow(row)
    return path


def main() -> None:
    args = parse_args()
    files = sorted(args.source.glob("**/*.trades.dbn.zst"))
    if not files:
        raise SystemExit(f"No trade DBN files under {args.source}")
    args.out.mkdir(parents=True, exist_ok=True)
    dominant = select_dominant(files, args.chunk_records)
    current_day = ""
    seconds: dict[pd.Timestamp, dict[str, object]] = {}
    written = []
    for path in files:
        for frame in frames(path, args.chunk_records):
            frame = clean(frame)
            if frame.empty:
                continue
            frame = frame[frame["day"].map(dominant).eq(frame["symbol"])]
            for row in frame.itertuples(index=False):
                if current_day and row.day != current_day:
                    written.append(str(write_day(args.out, current_day, seconds)))
                    seconds = {}
                current_day = row.day
                second = row.ts_event.floor("s")
                item = seconds.setdefault(second, empty_second())
                add_trade(item, float(row.price), int(row.size), str(row.side))
    if current_day:
        written.append(str(write_day(args.out, current_day, seconds)))
    manifest = {
        "source": str(args.source),
        "selection_rule": "highest total outright MNQ trade volume per UTC calendar day",
        "side_mapping": {"A": "sell_volume", "B": "buy_volume", "N": "unknown_volume"},
        "side_mapping_source": "https://databento.com/docs/schemas-and-data-formats/trades",
        "dominant_contract_by_day": dominant,
        "partitions": written,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print(f"Wrote {len(written)} canonical partitions to {args.out}")


if __name__ == "__main__":
    main()
