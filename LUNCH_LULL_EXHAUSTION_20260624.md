# Lunch Lull Exhaustion Verdict

Issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/27
Parent roadmap: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/21

Verdict: `session_regime_proxy_diagnostic_only`

This is a Phase 1 state-variable audit only. It does not run RSI or any other strategy signal and cannot approve trading.

## Interpretation

- Morning exhaustion shows enough diagnostic separation to continue research, but remains non-tradable by itself.
- Any lunch VWAP or range-contraction signal test must be opened as a separate issue.

Gate reasons:
- none

Guardrails:
- No RSI or other strategy signal was run.
- No paper/live approval.
- No NinjaTrader execution.
- No broker/IBKR work.
- No primary validation candidate.

## Primary Summary

| Root | State | Days | Median lunch range / morning range | Contraction rate | VWAP cross rate | Continuation failure rate |
|---|---|---:|---:|---:|---:|---:|
| MNQ | unconditional | 753 | 0.700 | 0.210 | 0.599 | 0.479 |
| MNQ | standard | 619 | 0.735 | 0.162 | 0.633 | 0.477 |
| MNQ | exhaustion | 134 | 0.522 | 0.433 | 0.440 | 0.493 |
| NQ | unconditional | 753 | 0.698 | 0.211 | 0.596 | 0.479 |
| NQ | standard | 618 | 0.735 | 0.163 | 0.629 | 0.476 |
| NQ | exhaustion | 135 | 0.524 | 0.430 | 0.444 | 0.496 |

## Artifacts

- Report directory: `reports/lunch_lull_exhaustion_20260624`
- Required tables: `morning_state_summary.csv`, `lunch_outcomes_by_morning_state.csv`, `vwap_reversion_metrics.csv`, `trend_continuation_failure_metrics.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.
- Final verdict: `session_regime_proxy_diagnostic_only`.
