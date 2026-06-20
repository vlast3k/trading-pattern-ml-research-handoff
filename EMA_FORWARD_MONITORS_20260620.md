# EMA Forward Monitors - 2026-06-20

GitHub tracker: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/8

Issue #8 freezes EMA as diagnostics only. It does not search new EMA variants,
tune parameters, implement NinjaTrader code, or make a paper/live trading
decision.

## Frozen Monitors

1. `local_raw_60m_ema_pullback`
   - Input family: MNQ 60m `ema_pullback_trend`
   - Filter: no context filter
   - Purpose: test whether recent local 60m EMA behavior persists forward

2. `databento_style_15m_ema_month_or_week_down`
   - Input family: MNQ 15m `ema_pullback_trend`
   - Filter: `month_trend == "down" OR week_trend == "down"`
   - Purpose: test whether the historical Databento-style 15m down-trend EMA
     behavior recurs locally

## Runner

Script:

- `scripts/run_ema_forward_monitor.py`

Default inputs:

- `reports/ema_pullback_reconciliation_20260619/local_context_15_30_60/trades_with_context.csv.gz`
- `reports/ninja_canonical_ohlcv_eval_20260619_expanded/trades_nonoverlap.csv.gz`
- `reports/ninja_canonical_ohlcv_eval_20260619_expanded/manifest.json`

Default output:

- `reports/ema_forward_monitor_20260620/VERDICT.md`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.csv`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.json`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_config.json`
- `reports/ema_forward_monitor_20260620/join_checks.csv`
- `reports/ema_forward_monitor_20260620/selected_trades.csv.gz`

## Cost And Cadence

The source trade PnL already includes the source evaluator's `$2.24`
round-turn commission and zero slippage. The runner adds slippage sensitivity
at `0`, `1`, and `2` ticks per side. For MNQ, one tick per side subtracts
`$1.00` per trade.

Forward monitoring cadence is weekly, with monthly rollups. The runner should
be rerun only after newly appended local canonical trades are explicitly
available. The monitor definitions must not be retuned between runs.

## Current Recommendation

Keep only one active frozen EMA monitor: `local_raw_60m_ema_pullback`.

The Databento-style 15m month/week down-trend monitor remains a historical
reference diagnostic, but it should not be treated as an active local forward
monitor unless future appended data produces enough trades and positive net/PF
without retuning.
