# Source Lineage

Generated: 2026-06-24T20:19:49.802551+00:00

| Source | Path | File size bytes | Rows | First | Last | Role |
|---|---|---:|---:|---|---|---|
| databento_ohlcv_1m_full_view | `../trading/data/databento_ohlcv_1m/front_1m.parquet` | 40758404 | 2295226 | 2023-01-02T23:00:00+00:00 | 2026-03-31T23:59:00+00:00 | primary_and_supplemental_source |
| local_ninja_ohlcv_1m | `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet` | 1943862 | 124112 | 2026-04-01T11:00:00+00:00 | 2026-06-08T09:57:00+00:00 | under_sampled_recency_sanity_only |

## Session Convention

Timezone: `America/New_York`.
RTH morning state window: `09:30` through `11:30`.
Lunch target window: `11:30` through `14:00`.

## Metric Definitions

`Lunch_range_contraction`: lunch range < morning range * `0.5`.
`Lunch_trendiness`: abs(lunch close - lunch open) / max(lunch high - lunch low, tick size).
`VWAP`: HLC3 volume-weighted average price over the completed morning window.
`VWAP_cross`: lunch high/low spans the completed morning VWAP.
`VWAP_touch_after_morning_extension`: morning close differs from morning VWAP and lunch spans that morning VWAP.
`Trend_continuation_failure`: lunch signed direction is opposite the morning signed direction.
`New_high_or_low_during_lunch`: lunch high exceeds morning high or lunch low breaks morning low.
`Close_location_within_lunch_range`: (lunch close - lunch low) / max(lunch range, tick size).

## Data Windows

Primary Databento window: `2023-01-01` through `2025-12-31`.
Supplemental Databento window: `2026-01-01` through `2026-03-31` when requested.
Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.

## Lookahead Guard

Morning state uses only the completed 09:30-11:30 morning window and prior completed morning sessions. Lunch outcomes are measured after 11:30 and are not used for state classification.
