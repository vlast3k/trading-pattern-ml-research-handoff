# ATR Regime Conditioning Verdict

Issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/19

Verdict: `regime_proxy_useful_but_no_signal_edge`

This is a regime-conditioning research audit. It cannot approve paper/live trading and cannot directly promote a primary validation candidate.

## Phase 1

Status: pass

Reasons:
- none

Interpretation:
- The ATR proxy separates next-day range directionally, but the spread is modest and noisy.
- Neutral and expansion median ranges are close, and diagnostic bins are not monotonic enough to imply a stable structural regime.
- This is a lagging realized-volatility state proxy, not evidence of a structural dealer-gamma regime.
- Treat the result as permission to continue diagnostics, not as proof of a useful trading regime.

## Phase 2

Requested: True
Ran: true
RSI status: `rsi_exact_frozen_definition_not_recovered_without_inference`

Interpretation:
- Simple Donchian 60m is diagnostic only and is not the failed confluence candidate.
- RSI reversion is unavailable unless the exact frozen definition is recovered without inference.
- No row in this issue can approve strategy promotion by itself.

Guardrails:
- Forbidden verdicts: pass_forward_validation, paper_ready, live_ready, primary_validation_candidate.
- Any candidate validation must be opened as a separate issue.

## Phase 1 State Summary

| Root | Compression days | Neutral days | Expansion days | Compression median range | Expansion median range | Expansion > compression |
|---|---:|---:|---:|---:|---:|---|
| MNQ | 340 | 290 | 285 | 221.0 | 261.75 | True |
| NQ | 340 | 288 | 287 | 220.5 | 262.75 | True |

## Phase 2 Donchian Diagnostic

| Root | State | Trades | Net dollars | PF | Gate pass |
|---|---|---:|---:|---:|---|
| MNQ | compression | 449 | -2296.50 | 0.915 | False |
| MNQ | neutral | 399 | 2155.50 | 1.083 | False |
| MNQ | expansion | 348 | -5924.50 | 0.790 | False |
| NQ | compression | 452 | -7570.00 | 0.971 | False |
| NQ | neutral | 400 | 19725.00 | 1.076 | False |
| NQ | expansion | 348 | -58395.00 | 0.794 | False |

This is a diagnostic A/B only. It is not a validation of the failed Donchian confluence candidate and does not promote a strategy.

## Interpretation

- Phase 1 separation is modest/noisy: expansion has higher median range than compression, but this is only a lagging realized-volatility proxy.
- Neutral and expansion medians are close, and diagnostic bins are not monotonic enough to treat the state proxy as structurally proven.
- The proxy must not be described as actual gamma exposure or a proven structural market regime.
- RSI remains unavailable because the exact frozen definition was not recovered without inference.
- Local Ninja parity is under-sampled and should be read as sanity/recency context only, not confirmatory validation.

## Generated Artifacts

- Report directory: `reports/atr_regime_conditioning_20260621`
- Main tables: `state_distribution_by_year.csv`, `next_day_behavior_by_state.csv`, `bin_grid_diagnostics.csv`, `local_ninja_parity_check.csv`.
- Signal tables contain the diagnostic Donchian A/B when `--run-phase2` is used, plus explicit RSI unavailable rows.
