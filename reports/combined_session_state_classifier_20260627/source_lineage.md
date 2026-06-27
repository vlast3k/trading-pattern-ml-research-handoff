# Source Lineage

Generated: 2026-06-27T08:08:44.686615+00:00

| Source | Path | Rows | Role |
|---|---|---:|---|
| coiled_spring | `reports/coiled_spring_globex_rth_morning_20260624/session_state_table.csv` | 1546 | primary_merged_child_issue_table |
| lunch_lull | `reports/lunch_lull_exhaustion_20260624/session_state_table.csv` | 1546 | primary_merged_child_issue_table |
| inside_day_trap | `reports/inside_day_trap_20260624/session_state_table.csv` | 1546 | primary_merged_child_issue_table |
| databento_ohlcv_1m_full_view | `../trading/data/databento_ohlcv_1m/front_1m.parquet` | 126 | supplemental_recomputed_child_states |
| local_ninja_ohlcv_1m | `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet` | 96 | under_sampled_recency_sanity_only |

## Combination Method

Primary evidence joins the merged child issue session-state tables on `root` and `session_date`.
Supplemental and local parity tables, when requested, are rebuilt through the accepted child audit scripts using their frozen state definitions and the same source data conventions.

No model is trained. No thresholds are optimized. Only predeclared intersections from Issue #24 are evaluated.

## Data Windows

Primary window: `2023-01-01` through `2025-12-31`.
Supplemental window: `2026-01-01` through `2026-03-31` when requested.
Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.
