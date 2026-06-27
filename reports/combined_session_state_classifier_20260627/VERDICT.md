# Combined Session-State Classifier Verdict

Issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/24
Parent roadmap: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/21

Verdict: `session_regime_proxy_rejected`

This is a combined Phase 1 state-classifier audit only. It does not run RSI, VWAP-reversion, continuation, Donchian, or any other strategy signal and cannot approve trading.

## Interpretation

- The fixed combined intersections did not materially improve over the relevant best individual state inputs under the frozen gates.
- The strongest individual input remains Lunch Lull Exhaustion from Issue #27; adding Globex or first-hour labels did not create a superior lunch classifier.
- Some intersections look better in-sample, but the promising lunch-compression subset is too sparse to accept.

Gate reasons:
- MNQ:globex_compression__inside_trapped:too_sparse:19
- MNQ:globex_compression__morning_exhaustion:too_sparse:12
- MNQ:morning_exhaustion__inside_trapped:too_sparse:15
- NQ:globex_compression__inside_trapped:too_sparse:18
- NQ:globex_compression__morning_exhaustion:too_sparse:12
- NQ:morning_exhaustion__inside_trapped:too_sparse:15
- no_non_sparse_combined_state_materially_improves_best_individual_across_required_metrics

Guardrails:
- No strategy signal was run.
- No RSI was run or inferred.
- No paper/live approval.
- No NinjaTrader execution.
- No broker/IBKR work.
- No primary validation candidate.

## Lunch Comparison Against Best Individual

| Root | Combined State | Metric | Best Individual | Best Value | Combined Value | Lift vs Best |
|---|---|---|---|---:|---:|---:|
| MNQ | globex_compression__morning_exhaustion | lunch_range_contraction_rate | morning_exhaustion | 0.433 | 0.583 | 0.150 |
| MNQ | globex_compression__morning_exhaustion | median_lunch_range_div_morning_range | morning_exhaustion | 0.522 | 0.394 | 0.128 |
| MNQ | globex_expansion__morning_exhaustion | lunch_range_contraction_rate | morning_exhaustion | 0.433 | 0.385 | -0.048 |
| MNQ | globex_expansion__morning_exhaustion | median_lunch_range_div_morning_range | morning_exhaustion | 0.522 | 0.596 | -0.075 |
| MNQ | morning_exhaustion__inside_broken | lunch_range_contraction_rate | morning_exhaustion | 0.433 | 0.445 | 0.013 |
| MNQ | morning_exhaustion__inside_broken | median_lunch_range_div_morning_range | morning_exhaustion | 0.522 | 0.521 | 0.000 |
| MNQ | morning_exhaustion__inside_trapped | lunch_range_contraction_rate | morning_exhaustion | 0.433 | 0.333 | -0.100 |
| MNQ | morning_exhaustion__inside_trapped | median_lunch_range_div_morning_range | morning_exhaustion | 0.522 | 0.682 | -0.160 |
| NQ | globex_compression__morning_exhaustion | lunch_range_contraction_rate | morning_exhaustion | 0.430 | 0.583 | 0.154 |
| NQ | globex_compression__morning_exhaustion | median_lunch_range_div_morning_range | morning_exhaustion | 0.524 | 0.394 | 0.130 |
| NQ | globex_expansion__morning_exhaustion | lunch_range_contraction_rate | morning_exhaustion | 0.430 | 0.377 | -0.053 |
| NQ | globex_expansion__morning_exhaustion | median_lunch_range_div_morning_range | morning_exhaustion | 0.524 | 0.601 | -0.077 |
| NQ | morning_exhaustion__inside_broken | lunch_range_contraction_rate | morning_exhaustion | 0.430 | 0.442 | 0.012 |
| NQ | morning_exhaustion__inside_broken | median_lunch_range_div_morning_range | morning_exhaustion | 0.524 | 0.524 | 0.000 |
| NQ | morning_exhaustion__inside_trapped | lunch_range_contraction_rate | morning_exhaustion | 0.430 | 0.333 | -0.096 |
| NQ | morning_exhaustion__inside_trapped | median_lunch_range_div_morning_range | morning_exhaustion | 0.524 | 0.675 | -0.151 |

## Rest-Of-RTH Comparison

| Root | Combined State | Metric | Best Individual | Best Value | Combined Value | Lift vs Best |
|---|---|---|---|---:|---:|---:|
| MNQ | globex_compression__inside_trapped | median_rest_rth_range_div_first_hour_range | inside_trapped | 1.538 | 2.097 | 0.559 |
| MNQ | globex_compression__inside_trapped | new_session_high_or_low_after_10_30_rate | inside_trapped | 0.776 | 0.789 | -0.014 |
| MNQ | globex_expansion__inside_broken | median_rest_rth_range_div_first_hour_range | globex_expansion | 1.302 | 1.275 | -0.027 |
| MNQ | globex_expansion__inside_broken | new_session_high_or_low_after_10_30_rate | inside_broken | 0.866 | 0.815 | -0.051 |
| NQ | globex_compression__inside_trapped | median_rest_rth_range_div_first_hour_range | inside_trapped | 1.537 | 2.226 | 0.689 |
| NQ | globex_compression__inside_trapped | new_session_high_or_low_after_10_30_rate | inside_trapped | 0.781 | 0.889 | -0.108 |
| NQ | globex_expansion__inside_broken | median_rest_rth_range_div_first_hour_range | globex_expansion | 1.297 | 1.285 | -0.012 |
| NQ | globex_expansion__inside_broken | new_session_high_or_low_after_10_30_rate | inside_broken | 0.868 | 0.825 | -0.043 |

## Artifacts

- Report directory: `reports/combined_session_state_classifier_20260627`
- Required tables: `state_inputs_used.json`, `combined_state_summary.csv`, `outcomes_by_combined_state.csv`, `comparison_single_vs_combined.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.
- Final verdict: `session_regime_proxy_rejected`.
