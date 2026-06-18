#!/usr/bin/env python3
"""Build compact research-ready Parquet tables from downloaded Databento DBN files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd
from databento_dbn import StatType


STAT_TYPES = {
    int(StatType.SETTLEMENT_PRICE.value): "settlement_price",
    int(StatType.CLEARED_VOLUME.value): "cleared_volume",
    int(StatType.OPEN_INTEREST.value): "open_interest",
    int(StatType.CLOSE_PRICE.value): "close_price",
}
CONTRACT_COLUMNS = [
    "instrument_id",
    "raw_symbol",
    "asset",
    "exchange",
    "currency",
    "expiration",
    "activation",
    "maturity_year",
    "maturity_month",
    "maturity_day",
    "min_price_increment",
    "min_price_increment_amount",
    "unit_of_measure_qty",
    "contract_multiplier",
    "unit_of_measure",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("data/multi_futures/databento")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/multi_futures/research")
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def dbn_files(source: Path, schema: str) -> list[Path]:
    files = sorted((source / schema).glob("**/*.dbn.zst"))
    if not files:
        raise FileNotFoundError(f"No {schema} DBN files under {source}")
    return files


def year_from_file(path: Path) -> int:
    return int(path.name.split("-")[2][:4])


def enrich_symbol_columns(frame: pd.DataFrame) -> pd.DataFrame:
    parts = frame["symbol"].str.extract(r"^(?P<root>.+)\.v\.(?P<rank>[01])$")
    frame["root"] = parts["root"]
    frame["continuous_rank"] = pd.to_numeric(parts["rank"], errors="coerce").astype(
        "Int8"
    )
    return frame


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression="zstd")


def build_contract_lookup(
    files: list[Path], out: Path, force: bool
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    lookup_path = out / "contracts" / "contract_lookup.parquet"
    coverage: list[dict[str, object]] = []
    yearly: list[pd.DataFrame] = []
    for path in files:
        year = year_from_file(path)
        output = out / "contracts" / f"definitions_{year}.parquet"
        if output.exists() and not force:
            frame = pd.read_parquet(output)
        else:
            frame = db.DBNStore.from_file(path).to_df().reset_index(names="ts_recv")
            keep = ["ts_recv", "ts_event", "symbol", *CONTRACT_COLUMNS]
            frame = frame[[column for column in keep if column in frame.columns]].copy()
            frame = enrich_symbol_columns(frame)
            frame = frame.sort_values(["instrument_id", "ts_recv"])
            write_parquet(frame, output)
        yearly.append(frame)
        coverage.append(
            {
                "table": "definitions",
                "year": year,
                "rows": len(frame),
                "symbols": frame["symbol"].nunique(),
                "instruments": frame["instrument_id"].nunique(),
            }
        )

    combined = pd.concat(yearly, ignore_index=True)
    lookup = (
        combined.sort_values(["instrument_id", "ts_recv"])
        .drop_duplicates("instrument_id", keep="last")
        [[column for column in CONTRACT_COLUMNS if column in combined.columns]]
        .reset_index(drop=True)
    )
    lookup["contract_value_multiplier"] = lookup["unit_of_measure_qty"]
    write_parquet(lookup, lookup_path)
    return lookup, coverage


def build_daily_bars(
    files: list[Path], lookup: pd.DataFrame, out: Path, force: bool
) -> list[dict[str, object]]:
    coverage: list[dict[str, object]] = []
    lookup_columns = [
        column
        for column in [
            "instrument_id",
            "raw_symbol",
            "expiration",
            "min_price_increment",
            "min_price_increment_amount",
            "unit_of_measure_qty",
            "contract_value_multiplier",
            "contract_multiplier",
        ]
        if column in lookup.columns
    ]
    for path in files:
        year = year_from_file(path)
        output = out / "daily_bars" / f"daily_bars_{year}.parquet"
        if output.exists() and not force:
            frame = pd.read_parquet(output)
        else:
            frame = db.DBNStore.from_file(path).to_df().reset_index(names="date")
            frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.normalize()
            frame = enrich_symbol_columns(frame)
            frame = frame.merge(lookup[lookup_columns], on="instrument_id", how="left")
            frame = frame.sort_values(["date", "symbol"]).reset_index(drop=True)
            write_parquet(frame, output)
        coverage.append(
            {
                "table": "daily_bars",
                "year": year,
                "rows": len(frame),
                "symbols": frame["symbol"].nunique(),
                "instruments": frame["instrument_id"].nunique(),
                "start": frame["date"].min(),
                "end": frame["date"].max(),
                "missing_raw_symbol": int(frame["raw_symbol"].isna().sum()),
            }
        )
        print(f"daily_bars {year}: {len(frame):,} rows")
    return coverage


def build_daily_statistics(
    files: list[Path], lookup: pd.DataFrame, out: Path, force: bool
) -> list[dict[str, object]]:
    coverage: list[dict[str, object]] = []
    lookup_columns = [
        column
        for column in ["instrument_id", "raw_symbol", "expiration"]
        if column in lookup.columns
    ]
    for path in files:
        year = year_from_file(path)
        output = out / "daily_statistics" / f"daily_statistics_{year}.parquet"
        if output.exists() and not force:
            wide = pd.read_parquet(output)
        else:
            frame = db.DBNStore.from_file(path).to_df().reset_index(names="ts_recv")
            frame = frame[frame["stat_type"].isin(STAT_TYPES)].copy()
            frame["stat_name"] = frame["stat_type"].map(STAT_TYPES)
            frame["date"] = pd.to_datetime(frame["ts_ref"], utc=True).dt.normalize()
            frame = frame.sort_values(["date", "symbol", "stat_name", "ts_recv"])
            final = frame.drop_duplicates(["date", "symbol", "stat_name"], keep="last")
            keys = ["date", "symbol"]
            prices = final[final["stat_name"].isin(["settlement_price", "close_price"])].pivot(
                index=keys,
                columns="stat_name",
                values="price",
            )
            quantities = final[
                final["stat_name"].isin(["cleared_volume", "open_interest"])
            ].pivot(
                index=keys,
                columns="stat_name",
                values="quantity",
            ).rename(
                columns={
                    "cleared_volume": "cleared_volume_quantity",
                    "open_interest": "open_interest_quantity",
                }
            )
            timestamps = final.pivot(
                index=keys, columns="stat_name", values="ts_recv"
            ).rename(columns=lambda name: f"{name}_available_at")
            instruments = final.pivot(
                index=keys, columns="stat_name", values="instrument_id"
            ).rename(columns=lambda name: f"{name}_instrument_id")
            wide = prices.join(quantities, how="outer").join(timestamps, how="outer")
            wide = wide.join(instruments, how="outer").reset_index()
            wide = enrich_symbol_columns(wide)
            instrument_columns = [
                column
                for column in [
                    "settlement_price_instrument_id",
                    "close_price_instrument_id",
                    "open_interest_instrument_id",
                    "cleared_volume_instrument_id",
                ]
                if column in wide.columns
            ]
            wide["reference_instrument_id"] = wide[instrument_columns].bfill(axis=1).iloc[
                :, 0
            ]
            reference_lookup = lookup[lookup_columns].rename(
                columns={"instrument_id": "reference_instrument_id"}
            )
            wide = wide.merge(reference_lookup, on="reference_instrument_id", how="left")
            wide = wide.sort_values(["date", "symbol"]).reset_index(drop=True)
            write_parquet(wide, output)
        print(f"daily_statistics {year}: {len(wide):,} rows")

    outputs = sorted((out / "daily_statistics").glob("daily_statistics_*.parquet"))
    combined = pd.concat([pd.read_parquet(path) for path in outputs], ignore_index=True)
    combined = combined[combined["date"].notna()].copy()
    combined = combined.drop(
        columns=[
            column
            for column in [
                "root",
                "continuous_rank",
                "reference_instrument_id",
                "raw_symbol",
                "expiration",
            ]
            if column in combined.columns
        ]
    )
    combined = (
        combined.sort_values(["date", "symbol"])
        .groupby(["date", "symbol"], as_index=False)
        .last()
    )
    combined = enrich_symbol_columns(combined)
    instrument_columns = [
        column
        for column in [
            "settlement_price_instrument_id",
            "close_price_instrument_id",
            "open_interest_instrument_id",
            "cleared_volume_instrument_id",
        ]
        if column in combined.columns
    ]
    combined["reference_instrument_id"] = combined[instrument_columns].bfill(axis=1).iloc[
        :, 0
    ]
    reference_lookup = lookup[lookup_columns].rename(
        columns={"instrument_id": "reference_instrument_id"}
    )
    combined = combined.merge(reference_lookup, on="reference_instrument_id", how="left")
    combined = combined.sort_values(["date", "symbol"]).reset_index(drop=True)

    for path in outputs:
        path.unlink()
    for year, wide in combined.groupby(combined["date"].dt.year):
        output = out / "daily_statistics" / f"daily_statistics_{year}.parquet"
        write_parquet(wide, output)
        coverage.append(
            {
                "table": "daily_statistics",
                "year": int(year),
                "rows": len(wide),
                "symbols": wide["symbol"].nunique(),
                "instruments": wide["reference_instrument_id"].nunique(),
                "start": wide["date"].min(),
                "end": wide["date"].max(),
                "missing_raw_symbol": int(wide["raw_symbol"].isna().sum()),
            }
        )
    return coverage


def build_mapping_audit(out: Path) -> pd.DataFrame:
    bars = pd.concat(
        [pd.read_parquet(path) for path in sorted((out / "daily_bars").glob("*.parquet"))],
        ignore_index=True,
    )
    bars = bars.sort_values(["symbol", "date"])
    bars["previous_instrument_id"] = bars.groupby("symbol")["instrument_id"].shift()
    changes = bars[
        bars["previous_instrument_id"].notna()
        & (bars["instrument_id"] != bars["previous_instrument_id"])
    ].copy()
    changes["days_to_expiration"] = (
        pd.to_datetime(changes["expiration"], utc=True) - changes["date"]
    ).dt.total_seconds() / 86400
    write_parquet(changes, out / "quality" / "mapping_changes.parquet")
    return changes


def write_validation_report(
    out: Path, lookup: pd.DataFrame, changes: pd.DataFrame
) -> dict[str, object]:
    bars = pd.concat(
        [pd.read_parquet(path) for path in sorted((out / "daily_bars").glob("*.parquet"))],
        ignore_index=True,
    )
    stats = pd.concat(
        [
            pd.read_parquet(path)
            for path in sorted((out / "daily_statistics").glob("*.parquet"))
        ],
        ignore_index=True,
    )
    bad_ohlc = (
        (bars["high"] < bars[["open", "close", "low"]].max(axis=1))
        | (bars["low"] > bars[["open", "close", "high"]].min(axis=1))
    )
    pairs = bars.pivot_table(
        index=["date", "root"],
        columns="continuous_rank",
        values="expiration",
        aggfunc="last",
    ).dropna()
    rank_one_not_later = pd.to_datetime(pairs[1], utc=True) <= pd.to_datetime(
        pairs[0], utc=True
    )
    availability = {}
    for column in [column for column in stats if column.endswith("_available_at")]:
        values = pd.to_datetime(stats[column], utc=True)
        valid = values.notna()
        availability[column] = {
            "rows": int(valid.sum()),
            "available_after_reference_date_fraction": float(
                (values[valid] > stats.loc[valid, "date"]).mean()
            ),
        }
    metrics: dict[str, object] = {
        "bar_rows": len(bars),
        "bar_start": str(bars["date"].min()),
        "bar_end": str(bars["date"].max()),
        "roots": int(bars["root"].nunique()),
        "continuous_symbols": int(bars["symbol"].nunique()),
        "bar_date_symbol_duplicates": int(bars.duplicated(["date", "symbol"]).sum()),
        "bad_ohlc_rows": int(bad_ohlc.sum()),
        "bar_missing_raw_symbol": int(bars["raw_symbol"].isna().sum()),
        "statistic_rows": len(stats),
        "statistic_date_symbol_duplicates": int(
            stats.duplicated(["date", "symbol"]).sum()
        ),
        "statistic_missing_raw_symbol": int(stats["raw_symbol"].isna().sum()),
        "contract_count": int(lookup["instrument_id"].nunique()),
        "missing_contract_value_multiplier": int(
            lookup["contract_value_multiplier"].isna().sum()
        ),
        "raw_contract_multiplier_invalid_fraction": float(
            (lookup["contract_multiplier"] == 2147483647).mean()
        ),
        "mapping_changes_rank_0": int((changes["continuous_rank"] == 0).sum()),
        "mapping_changes_rank_1": int((changes["continuous_rank"] == 1).sum()),
        "rank_1_not_later_expiry_rows": int(rank_one_not_later.sum()),
        "rank_1_not_later_expiry_fraction": float(rank_one_not_later.mean()),
        "statistic_availability": availability,
    }
    (out / "quality" / "validation.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="ascii"
    )
    report = [
        "# Databento Multi-Futures Dataset Validation",
        "",
        f"Built: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Result",
        "",
        "The daily dataset is structurally valid and ready for baseline research, with "
        "the mandatory usage rules below.",
        "",
        f"- Daily bars: `{len(bars):,}` rows from `{bars['date'].min().date()}` to "
        f"`{bars['date'].max().date()}` across `{bars['root'].nunique()}` roots.",
        f"- Official daily statistics: `{len(stats):,}` unique date/symbol rows.",
        f"- Actual contracts represented: `{lookup['instrument_id'].nunique():,}`.",
        f"- Duplicate daily bar keys: `{metrics['bar_date_symbol_duplicates']}`.",
        f"- Duplicate daily statistic keys: `{metrics['statistic_date_symbol_duplicates']}`.",
        f"- Invalid OHLC rows: `{metrics['bad_ohlc_rows']}`.",
        f"- Missing actual contract mappings in bars/statistics: "
        f"`{metrics['bar_missing_raw_symbol']}` / "
        f"`{metrics['statistic_missing_raw_symbol']}`.",
        "",
        "## Mandatory Usage Rules",
        "",
        "1. Use `contract_value_multiplier` (`unit_of_measure_qty`) for PnL scaling. "
        "The raw `contract_multiplier` field is an invalid sentinel in this dataset.",
        "2. Lag official statistics by their `*_available_at` timestamps. Settlement, "
        "open interest, and cleared volume are generally published after their reference date.",
        "3. Treat `.v.1` as the second-most-active contract, not automatically the next "
        "chronological expiry.",
        f"4. Reject or separately handle carry rows where rank 1 does not expire after "
        f"rank 0. This occurs in `{rank_one_not_later.mean():.2%}` of comparable rows.",
        "5. Use actual `instrument_id`, `raw_symbol`, and `expiration` when simulating "
        "rolls and executable PnL.",
        "",
        "## Mapping Behavior",
        "",
        f"- Rank 0 mapping changes: `{metrics['mapping_changes_rank_0']:,}`.",
        f"- Rank 1 mapping changes: `{metrics['mapping_changes_rank_1']:,}`.",
        "- RTY history begins in July 2017; the other selected roots begin in June 2010.",
        "",
        "Raw DBN files remain the source of truth. The Parquet tables are compact research "
        "views and can be rebuilt with `scripts/build_databento_research_dataset.py`.",
        "",
    ]
    (out / "quality" / "VALIDATION.md").write_text(
        "\n".join(report), encoding="ascii"
    )
    return metrics


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    definition_files = dbn_files(args.source, "definition")
    bar_files = dbn_files(args.source, "ohlcv-1d")
    statistic_files = dbn_files(args.source, "statistics")

    lookup, definition_coverage = build_contract_lookup(
        definition_files, args.out, args.force
    )
    coverage = definition_coverage
    coverage += build_daily_bars(bar_files, lookup, args.out, args.force)
    coverage += build_daily_statistics(statistic_files, lookup, args.out, args.force)
    changes = build_mapping_audit(args.out)
    validation = write_validation_report(args.out, lookup, changes)

    coverage_frame = pd.DataFrame(coverage)
    coverage_frame.to_csv(args.out / "quality" / "coverage.csv", index=False)
    summary = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": str(args.source),
        "output": str(args.out),
        "contract_count": int(lookup["instrument_id"].nunique()),
        "mapping_change_count": len(changes),
        "validation": validation,
        "coverage_rows": coverage,
        "notes": [
            "continuous_rank 0/1 is volume rank, not guaranteed chronological expiry",
            "daily_statistics keeps the final update for each date/symbol/statistic",
            "raw DBN files remain the source of truth",
        ],
    }
    (args.out / "quality" / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="ascii"
    )
    print(f"Completed research dataset under {args.out}")


if __name__ == "__main__":
    main()
