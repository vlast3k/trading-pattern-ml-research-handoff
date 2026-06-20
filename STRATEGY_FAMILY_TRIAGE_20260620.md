# Strategy Family Triage - 2026-06-20

This report supports Issue #9. It is a scaffolded ranking, not a deployment decision.

## Primary recommendation

**keep all families diagnostic and collect specific forward data**

Some evidence is positive, but no family clears validation-level gates.

## Ranked families

| Rank | Family | Status | Score | Best variant | Net | PF | Trades | Max DD | Net ex-largest | Caps / missing evidence | Source |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | `ema_pullback` | `diagnostic_only` | 118.0 | `ema_pullback_trend` | $2,478 | 1.31 | 66 | $1,015 | $1,575 | `family_status_cap:ema_pullback<=diagnostic_only` | `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.csv` |
| 2 | `unknown_other` | `diagnostic_only` | 90.0 | `cohort_payoff` | $1,021 | 2.82 | 54 | $137 | n/a | `missing_required_for_promotion:net_without_largest` | `reports/pattern_ml_20260612/payoff_asymmetry/cohort_payoff.csv` |
| 3 | `multi_timeframe_regime_selector` | `diagnostic_only` | 55.0 | `cohort_stability` | $1,021 | n/a | 54 | $137 | n/a | `missing_required_for_promotion:profit_factor,largest_winner_share,net_without_largest` | `reports/pattern_ml_20260612/regime_shift/cohort_stability.csv` |
| 4 | `orb_vwap_prior_day` | `diagnostic_only` | 20.0 | `vwap_delta_rejection` | $178 | n/a | n/a | n/a | n/a | `profit_factor,max_drawdown_dollars,trades,largest_winner_share,net_without_largest` | `reports/mnq_2025q1_primary_replication/primary_nonoverlapping_trades.csv` |

## Worker notes

- If a known overfit or wrong-cohort row ranks first, override the scaffold in the final product conclusion.
- Final Issue #9 recommendation must be exactly one of the three choices in the issue body.

## Skipped CSV files

| File | Reason |
|---|---|
| `reports/mnq_2025q1_primary_replication/mnq_databento_day_regime_selector.csv` | `no_mapped_metric_columns` |
| `reports/mnq_2025q1_primary_replication/mnq_databento_day_regimes.csv` | `no_mapped_metric_columns` |
| `reports/mnq_2025q1_primary_replication/mnq_databento_regime_filters.csv` | `no_mapped_metric_columns` |
| `reports/mnq_2025q1_primary_replication/mnq_databento_regime_trades.csv` | `no_mapped_metric_columns` |
| `reports/mnq_2025q1_primary_replication/mnq_databento_trades.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/analog_neighbors.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/formula_filter_summary.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/formula_filter_threshold_selection.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/random_controls.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/regime_shift/feature_drift.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/regime_shift/outcome_association.csv` | `no_mapped_metric_columns` |
| `reports/pattern_ml_20260612/threshold_selection.csv` | `no_mapped_metric_columns` |
