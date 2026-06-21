# Next Iteration Retriage Verdict

Issue: [#13](https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/13)

Verdict: `collect_specific_data_first`

There is **no active primary validation candidate** after the Issue #11 Donchian demotion.

## Decision

First rebuild/import a fresh canonical post-selection OHLCV/order-flow source from raw Ninja exports/replay/live data, then collect/import a specific repo-relative forward package before choosing another candidate:

```text
data/local_canonical/post_selection_forward_20260609_plus/
```

This is not a request for generic more history. It is a targeted forward package starting after the existing local research/selection window ending around `2026-06-08`, with repo-relative lineage and frozen diagnostic outputs.

The existing `../trading/data/ninja_canonical_ohlcv_1m/` source is not sufficient for this package because `DATA_INVENTORY.md` records it ending at `2026-06-08T09:57:00+00:00`. The next worker must rebuild/import a newer canonical OHLCV/order-flow source from raw Ninja exports/replay/live data before packaging the eligible post-selection slice.

## Why Not Advance A Family Now

- Donchian failed the available-data audit robustness gates: largest winner 52.4%, best day 83.0%, best week 117.1%.
- EMA is the best surviving diagnostic monitor, but cross-source support remains unresolved.
- RSI has a relatively clean local row, but independent Databento support is sparse and no frozen forward monitor exists.
- Prior-day/ORB/VWAP and Bollinger have historical hints but no clean frozen local confirmation.
- MACD has strong Databento rows but failed local confirmation.
- Raw SFP/order-flow reversal remains rejected by independent 2025Q1 replication.

## Required Forward Package

Minimum contents:

- `IMPORT_MANIFEST.json`
- `source_lineage.md`
- OHLCV/order-flow context from a fresh canonical source that extends beyond `2026-06-08`; do not reuse the stale `../trading/data/ninja_canonical_ohlcv_1m/` selection-window source as forward data
- frozen diagnostic outputs for `local_raw_60m_ema_pullback`
- frozen diagnostic outputs for RSI, prior-day/ORB/VWAP, and Bollinger only if exact definitions are recoverable
- explicit `not_available` rows where definitions cannot be recovered

Minimum decision threshold:

- 4 calendar weeks after `2026-06-08`
- preferably 30 trades per frozen diagnostic candidate before judging
- positive net after costs
- PF >= 1.10 baseline and >= 1.05 under 2 ticks per side slippage
- max drawdown compatible with one MNQ contract
- largest-winner share < 50%
- best-day and best-week concentration < 50%
- net excluding largest winner > 0

## Status Updates

- Donchian / range breakout: `diagnostic_only`
- EMA pullback: `diagnostic_only`
- RSI reversion: `diagnostic_only`
- Prior-day / ORB / VWAP level variants: `diagnostic_only`
- Bollinger / volatility expansion: `diagnostic_only`
- MACD / momentum: `diagnostic_only`
- Raw SFP / order-flow reversal: `reject`

No paper/live trading, NinjaTrader order automation, IBKR/broker integration, Donchian retuning, or broad parameter discovery is recommended.

