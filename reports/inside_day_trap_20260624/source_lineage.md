# Source Lineage

Generated: 2026-06-24T20:29:49.692313+00:00

| Source | Path | File size bytes | Rows | First | Last | Role |
|---|---|---:|---:|---|---|---|
| databento_ohlcv_1m_full_view | `../trading/data/databento_ohlcv_1m/front_1m.parquet` | 40758404 | 2295226 | 2023-01-02T23:00:00+00:00 | 2026-03-31T23:59:00+00:00 | primary_and_supplemental_source |
| local_ninja_ohlcv_1m | `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet` | 1943862 | 124112 | 2026-04-01T11:00:00+00:00 | 2026-06-08T09:57:00+00:00 | under_sampled_recency_sanity_only |

## Session Convention

Timezone: `America/New_York`.
Globex boundary window: `18:00` prior local date through `09:30` current local date.
First RTH hour state window: `09:30` through `10:30`.
Rest-of-RTH target window: `10:30` through `16:00`.

## State Definition

`trapped`: first-hour high is strictly below Globex high and first-hour low is strictly above Globex low.
`broken`: first-hour high reaches/exceeds Globex high or first-hour low reaches/breaks Globex low.
`broken_up`, `broken_down`, `broken_both`, and `near_boundary_but_not_broken` are diagnostic sub-states only.

## Metric Definitions

`rest_RTH_range`: high minus low from 10:30 through 16:00.
`rest_RTH_range / first_hour_range`: rest-of-RTH range divided by completed first-hour range.
`rest_RTH_trendiness`: abs(rest close - rest open) / max(rest range, tick size).
`rotation_count`: count close-to-close sign changes inside rest-of-RTH after ignoring zero moves.
`chop_index`: rotation_count / max(nonzero close move count - 1, 1).
`VWAP_cross_count`: count of rest-of-RTH 1-minute bars spanning the completed first-hour HLC3 volume-weighted VWAP.
`new_RTH_high_after_10_30`: rest high exceeds first-hour high.
`new_RTH_low_after_10_30`: rest low breaks first-hour low.
`new_session_high_or_low_after_10_30`: rest breaks max(Globex high, first-hour high) or min(Globex low, first-hour low).

## Lookahead Guard

State classification uses only the completed Globex boundary window and completed 09:30-10:30 first-hour window. Rest-of-RTH outcomes are measured only after 10:30.

## Data Windows

Primary Databento window: `2023-01-01` through `2025-12-31`.
Supplemental Databento window: `2026-01-01` through `2026-03-31` when requested.
Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.
