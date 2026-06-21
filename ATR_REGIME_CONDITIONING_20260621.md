# ATR Regime Conditioning Verdict

Issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/19

Verdict: `incomplete_reproducibility`

This is a regime-conditioning research audit. It cannot approve paper/live trading and cannot directly promote a primary validation candidate.

## Phase 1

Status: pass

Reasons:
- none

## Phase 2

Requested: False
Ran: false
Skip reason: `phase2_not_implemented_in_initial_scaffold`

Interpretation:
- If Phase 1 passes, this scaffold still reports `incomplete_reproducibility` because signal definitions and Phase 2 controls have not been executed.
- A worker must extend or run Phase 2 in a later commit before claiming signal-edge results.

Guardrails:
- Forbidden verdicts: pass_forward_validation, paper_ready, live_ready, primary_validation_candidate.
- Any candidate validation must be opened as a separate issue.

## Phase 1 State Summary

| Root | Compression days | Neutral days | Expansion days | Compression median range | Expansion median range | Expansion > compression |
|---|---:|---:|---:|---:|---:|---|
| MNQ | 361 | 319 | 312 | 230.25 | 268.5 | True |
| NQ | 361 | 317 | 314 | 230.0 | 270.375 | True |

## Generated Artifacts

- Report directory: `reports/atr_regime_conditioning_20260621`
- Main tables: `state_distribution_by_year.csv`, `next_day_behavior_by_state.csv`, `bin_grid_diagnostics.csv`, `local_ninja_parity_check.csv`.
- Signal tables are placeholders with explicit skip reasons because Phase 2 was not run in this scaffold.
