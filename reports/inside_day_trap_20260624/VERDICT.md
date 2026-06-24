# Inside Day Trap Verdict

Issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/23
Parent roadmap: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/21

Verdict: `session_regime_proxy_diagnostic_only`

This is a Phase 1 state-variable audit only. It does not run RSI, continuation, VWAP-reversion, or any other strategy signal and cannot approve trading.

## Interpretation

- First-hour containment versus Globex shows diagnostic separation, but remains non-tradable by itself.
- Any continuation or VWAP-reversion signal test must be opened as a separate frozen diagnostic issue.

Gate reasons:
- none

Guardrails:
- No RSI or other strategy signal was run.
- No paper/live approval.
- No NinjaTrader execution.
- No broker/IBKR work.
- No primary validation candidate.

## Primary Summary

| Root | State | Days | Median rest / first-hour range | New RTH extreme rate | New session extreme rate | Mean chop index | Mean first-hour VWAP cross count |
|---|---|---:|---:|---:|---:|---:|---:|
| MNQ | broken | 612 | 1.290 | 0.961 | 0.866 | 0.510 | 13.87 |
| MNQ | trapped | 161 | 1.519 | 1.000 | 0.770 | 0.506 | 15.03 |
| MNQ | unconditional | 773 | 1.344 | 0.969 | 0.846 | 0.509 | 14.11 |
| NQ | broken | 613 | 1.291 | 0.962 | 0.868 | 0.509 | 13.54 |
| NQ | trapped | 160 | 1.534 | 1.000 | 0.775 | 0.507 | 14.72 |
| NQ | unconditional | 773 | 1.348 | 0.970 | 0.849 | 0.509 | 13.79 |

## Artifacts

- Report directory: `reports/inside_day_trap_20260624`
- Required tables: `inside_trap_state_summary.csv`, `rest_of_rth_outcomes_by_state.csv`, `new_high_low_metrics.csv`, `chop_rotation_metrics.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.
- Final verdict: `session_regime_proxy_diagnostic_only`.
