# EMA Forward Monitor - 2026-06-20

This report evaluates exactly two frozen EMA diagnostic monitors from GitHub issue #8. It does not tune EMA parameters, search variants, implement NinjaTrader code, or make a paper/live trading decision.

## Verdict

Recommendation: `keep only one frozen monitor`.

EMA remains `diagnostic_only`: the local raw 60m monitor passes the frozen full-cohort diagnostic thresholds in the currently available existing local baseline cohort, but the Databento-style 15m down-trend monitor fails and the original cross-source mismatch from issue #7 is not resolved.

- `local_raw_60m_ema_pullback` passes all full-cohort slippage scenarios: `True`.
- `databento_style_15m_ema_month_or_week_down` passes all full-cohort slippage scenarios: `False`.

## Inputs

- Context trades: `reports/ema_pullback_reconciliation_20260619/local_context_15_30_60/trades_with_context.csv.gz`
- Raw trades for join validation: `reports/ninja_canonical_ohlcv_eval_20260619_expanded/trades_nonoverlap.csv.gz`
- Source manifest: `reports/ninja_canonical_ohlcv_eval_20260619_expanded/manifest.json`
- Forward window: `all_available_explicit_context` to `open`
- Cohort label: `existing_local_baseline_not_newly_appended_forward`
- Cadence: weekly monitoring plus monthly rollup; rerun whenever newly appended local canonical trades are available.

## Frozen Monitors

| Monitor | Definition | Thresholds |
|---|---|---|
| `local_raw_60m_ema_pullback` | Local raw MNQ 60m EMA pullback; tests whether recent local 60m behavior persists. Filter: `No context filter.` | trades >= 30; weeks >= 4; PF >= 1.1; net ex-largest > $0; largest share <= 40%; DD <= $1,500 |
| `databento_style_15m_ema_month_or_week_down` | Databento-style MNQ 15m EMA pullback when prior month or week trend is down. Filter: `month_trend == 'down' OR week_trend == 'down'.` | trades >= 30; weeks >= 4; PF >= 1.1; net ex-largest > $0; largest share <= 40%; DD <= $3,500 |

## Join Checks

| Check | Status | Count | Detail |
|---|---|---:|---|
| raw_key_duplicates | pass | 0 | root/timeframe/variant/entry_time duplicate keys in raw trades |
| context_key_duplicates | pass | 0 | root/timeframe/variant/entry_time duplicate keys in context trades |
| context_to_raw_key_match | pass | 0 | context rows without raw root/timeframe/variant/entry_time match |
| context_trade_id_duplicates | pass | 0 | duplicate context trade_id values |
| required_context_features | pass | 0 |  |

## Baseline Results

| Monitor | Trades | Weeks | Net | PF | Max DD | Largest Share | Net Ex Largest | Status | Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `local_raw_60m_ema_pullback` | 66 | 9 | $2,478 | 1.31 | $1,015 | 36.4% | $1,575 | pass |  |
| `databento_style_15m_ema_month_or_week_down` | 22 | 3 | $-1,287 | 0.44 | $1,404 |  | $-1,697 | fail | sample_size,calendar_coverage,net_not_positive,largest_winner_dependency,profit_factor |

## Slippage Sensitivity

| Monitor | Slippage Ticks/Side | Net | PF | Max DD | Net Ex Largest | Status | Reasons |
|---|---:|---:|---:|---:|---:|---|---|
| `local_raw_60m_ema_pullback` | 0.0 | $2,478 | 1.31 | $1,015 | $1,575 | pass |  |
| `local_raw_60m_ema_pullback` | 1.0 | $2,412 | 1.30 | $1,023 | $1,510 | pass |  |
| `local_raw_60m_ema_pullback` | 2.0 | $2,346 | 1.29 | $1,031 | $1,445 | pass |  |
| `databento_style_15m_ema_month_or_week_down` | 0.0 | $-1,287 | 0.44 | $1,404 | $-1,697 | fail | sample_size,calendar_coverage,net_not_positive,largest_winner_dependency,profit_factor |
| `databento_style_15m_ema_month_or_week_down` | 1.0 | $-1,309 | 0.43 | $1,422 | $-1,718 | fail | sample_size,calendar_coverage,net_not_positive,largest_winner_dependency,profit_factor |
| `databento_style_15m_ema_month_or_week_down` | 2.0 | $-1,331 | 0.43 | $1,440 | $-1,739 | fail | sample_size,calendar_coverage,net_not_positive,largest_winner_dependency,profit_factor |

## Decision

- Neither monitor should be promoted to `research_monitor` or paper trading.
- Keep only `local_raw_60m_ema_pullback` as the active frozen EMA monitor for the next forward period.
- `databento_style_15m_ema_month_or_week_down` fails on local data due to negative net/PF and sample size; keep it only as a historical-reference diagnostic, not an active local monitor.
- Further data need: continue forward monitoring only when newly appended local canonical data exists. Do not download old Databento data to rescue EMA.
