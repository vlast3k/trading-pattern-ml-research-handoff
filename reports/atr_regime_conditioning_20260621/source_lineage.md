# Source Lineage

Generated: 2026-06-22T04:20:55.748602+00:00

| Source | Path | File size bytes | Rows | First | Last | Role |
|---|---|---:|---:|---|---|---|
| databento_ohlcv_1m | `../trading/data/databento_ohlcv_1m/front_1m.parquet` | 40758404 | 2122069 | 2023-01-02T23:00:00+00:00 | 2025-12-31T21:59:00+00:00 | primary_long_history |
| local_ninja_ohlcv_1m | `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet` | 1943862 | 124112 | 2026-04-01T11:00:00+00:00 | 2026-06-08T09:57:00+00:00 | local_parity_under_sampled_recency_sanity_only |

## Session convention

Daily session date = timestamp converted to `America/New_York` and local calendar date.
Session convention label: `calendar_date_after_converting_utc_bars_to_America_New_York; document if changed before interpreting results`.

## Primary data window

Primary Databento output is filtered to `primary_2023_2025`: `2023-01-01` through `2025-12-31`.
Supplemental windows, when requested, are written separately and are not pooled into the primary verdict.

## Local Ninja parity

Local Ninja parity is a small recency sanity check only. Its state counts are under-sampled and must not be treated as confirmatory evidence.

## Lookahead guard

State for day t uses prior-day TR and ATR over completed prior sessions only. Current-day high/low is not included in the state for that day.

## Scope guard

This audit cannot approve paper/live trading and cannot directly promote a candidate.
