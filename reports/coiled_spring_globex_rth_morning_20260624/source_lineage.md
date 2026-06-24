# Source Lineage

Generated: 2026-06-24T20:10:08.842098+00:00

| Source | Path | File size bytes | Rows | First | Last | Role |
|---|---|---:|---:|---|---|---|
| databento_ohlcv_1m_full_view | `../trading/data/databento_ohlcv_1m/front_1m.parquet` | 40758404 | 2295226 | 2023-01-02T23:00:00+00:00 | 2026-03-31T23:59:00+00:00 | primary_and_supplemental_source |
| local_ninja_ohlcv_1m | `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet` | 1943862 | 124112 | 2026-04-01T11:00:00+00:00 | 2026-06-08T09:57:00+00:00 | under_sampled_recency_sanity_only |

## Session Convention

Timezone: `America/New_York`.
Globex context is `18:00` prior local date through `09:30` current local date, assigned to the current RTH session date.
RTH morning target is `09:30` through `11:30` on the same local session date.

## Metric Definitions

- `breached_Globex_high`: RTH morning high is above the completed Globex high.
- `breached_Globex_low`: RTH morning low is below the completed Globex low.
- `closed_outside_Globex_range`: RTH morning close is outside the completed Globex high/low range.
- `max_extension_beyond_Globex_range`: max positive extension above Globex high or below Globex low during RTH morning.
- `failed_breakout_reentry`: RTH morning breaches either Globex boundary and closes back inside the completed Globex range.

## Data Windows

Primary Databento window: `2023-01-01` through `2025-12-31`.
Supplemental Databento window: `2026-01-01` through `2026-03-31` when requested.
Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.

## Lookahead Guard

Globex state uses only completed Globex bars and a rolling median over prior completed Globex sessions. RTH morning outcomes are measured after the 09:30 open and are not used for state classification.
