# Source Lineage

Generated: 2026-06-21T20:58:58.945545+00:00

| Source | Path | File size bytes | Rows | First | Last | Role |
|---|---|---:|---:|---|---|---|
| databento_ohlcv_1m | `../trading/data/databento_ohlcv_1m/front_1m.parquet` | 40758404 | 2295226 | 2023-01-02T23:00:00+00:00 | 2026-03-31T23:59:00+00:00 | primary_long_history |
| local_ninja_ohlcv_1m | `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet` | 1943862 | 124112 | 2026-04-01T11:00:00+00:00 | 2026-06-08T09:57:00+00:00 | local_parity_recency_check |

## Session convention

Daily session date = timestamp converted to `America/New_York` and local calendar date.
Session convention label: `calendar_date_after_converting_utc_bars_to_America_New_York; document if changed before interpreting results`.

## Lookahead guard

State for day t uses prior-day TR and ATR over completed prior sessions only. Current-day high/low is not included in the state for that day.

## Scope guard

This scaffold writes Phase 2 placeholders only. It cannot approve paper/live trading and cannot directly promote a candidate.
