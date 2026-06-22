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
