# Coiled Spring Globex -> RTH Morning Verdict

Issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/22
Parent roadmap: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/21

Verdict: `session_regime_proxy_diagnostic_only`

This is a Phase 1 state-variable audit only. It does not run strategy signals and cannot approve paper/live trading.

## Interpretation

- Completed Globex range state shows enough diagnostic separation to continue research, but remains non-tradable by itself.
- Any signal test must be opened as a separate issue.

Gate reasons:
- none

Guardrails:
- No Donchian or other strategy signal was run.
- No paper/live approval.
- No NinjaTrader execution.
- No broker/IBKR work.
- No primary validation candidate.

## Primary Summary

| Root | State | Days | Median RTH morning range / ATR20 | Closed outside Globex rate | Failed breakout reentry rate |
|---|---|---:|---:|---:|---:|
| MNQ | unconditional | 753 | 0.596 | 0.501 | 0.368 |
| MNQ | compression | 160 | 0.437 | 0.556 | 0.388 |
| MNQ | neutral | 371 | 0.593 | 0.509 | 0.367 |
| MNQ | expansion | 222 | 0.740 | 0.446 | 0.356 |
| NQ | unconditional | 753 | 0.594 | 0.501 | 0.371 |
| NQ | compression | 165 | 0.437 | 0.545 | 0.412 |
| NQ | neutral | 368 | 0.593 | 0.519 | 0.353 |
| NQ | expansion | 220 | 0.724 | 0.436 | 0.368 |

## Artifacts

- Report directory: `reports/coiled_spring_globex_rth_morning_20260624`
- Required tables: `globex_state_summary.csv`, `rth_morning_outcomes_by_globex_state.csv`, `breakout_reentry_metrics.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.
- Final verdict: `session_regime_proxy_diagnostic_only`.
