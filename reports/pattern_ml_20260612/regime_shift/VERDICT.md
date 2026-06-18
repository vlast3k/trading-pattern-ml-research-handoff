# VWAP Delta Rejection Regime-Shift Diagnosis

This is a diagnostic audit, not a strategy-selection pass. All thresholds and predefined rules use development data only; the retrospective change point is explicitly marked post-hoc.

## Period Results

| Period | Trades | Profitable | Net PnL | Avg/trade | Max DD | Days + / - | Leave best day out |
|---|---:|---:|---:|---:|---:|---:|---:|
| `early_development` | 47 | 42.6% | $+219.44 | $+4.67 | $230.06 | 8 / 6 | $+49.36 |
| `late_development` | 83 | 36.1% | $-528.84 | $-6.37 | $725.02 | 5 / 17 | $-712.90 |
| `validation` | 19 | 63.2% | $+446.38 | $+23.49 | $108.46 | 5 / 0 | $+245.80 |
| `final_test` | 80 | 52.5% | $+845.60 | $+10.57 | $208.34 | 7 / 3 | $+462.18 |

## What Changed

- The profitable phase begins around the second half of May and is primarily a long/high-volatility phenomenon.
- A major replay-to-live provenance shift also occurred. It is a serious confounder, although later replay-only trades were profitable too, so it does not fully explain the result.
- The final block is profitable without its best day, but May 28 and May 29 still contribute a large share.

### Largest Feature Drifts

| Comparison | Feature | Dev median | Later median | Std mean diff | PSI | KS statistic |
|---|---|---:|---:|---:|---:|---:|
| `final_test` | `trade_live_ratio` | 0.0000 | 1.0000 | +2.220 | 10.636 | 0.738 |
| `final_test` | `quote_live_ratio` | 0.0000 | 1.0000 | +2.204 | 10.636 | 0.738 |
| `final_test` | `depth_live_ratio` | 0.0000 | 1.0000 | +2.158 | 10.574 | 0.738 |
| `final_test` | `rv_15m_atr` | 0.5949 | 0.7031 | +0.861 | 1.048 | 0.393 |
| `final_test` | `atr_14` | 11.7946 | 21.9107 | +0.809 | 3.224 | 0.474 |
| `final_test` | `range_1m_atr` | 1.4194 | 1.0542 | -0.798 | 1.972 | 0.433 |
| `final_test` | `signed_delta_pct` | 0.1937 | 0.1718 | -0.403 | 0.344 | 0.206 |
| `final_test` | `signed_ret_60m` | 0.0004 | 0.0007 | +0.398 | 0.400 | 0.186 |
| `validation` | `trade_live_ratio` | 0.0000 | 0.6000 | +1.532 | 7.511 | 0.579 |
| `validation` | `atr_14` | 11.7946 | 52.6964 | +1.507 | 8.494 | 0.789 |
| `validation` | `quote_live_ratio` | 0.0000 | 0.4000 | +1.469 | 7.511 | 0.579 |
| `validation` | `depth_live_ratio` | 0.0000 | 0.2333 | +1.323 | 8.213 | 0.632 |
| `validation` | `range_1m_atr` | 1.4194 | 0.6704 | -1.315 | 4.648 | 0.651 |
| `validation` | `spread_atr` | 0.0375 | 0.0104 | -1.307 | 9.568 | 0.785 |
| `validation` | `rv_15m_atr` | 0.5949 | 0.7947 | +1.272 | 4.337 | 0.492 |
| `validation` | `signed_delta_pct` | 0.1937 | 0.1380 | -0.918 | 2.969 | 0.360 |

## Predefined Rule Audit

A rule is chronologically eligible only if it has at least five trades, positive net PnL, and positive PnL after removing its best day in both early and late development. Validation/final results never make a rule eligible.

| Rule | Eligible before validation? | Early dev | Late dev | Validation | Final test |
|---|---|---:|---:|---:|---:|
| `all` | no | $+219.44 | $-528.84 | $+446.38 | $+845.60 |
| `high_volatility` | no | $-51.18 | $-212.02 | $+399.74 | $+910.28 |
| `higher_signed_delta` | no | $+101.98 | $-368.68 | $+42.64 | $+143.16 |
| `higher_volume` | no | $+175.46 | $-207.24 | $+24.06 | $-66.80 |
| `long_high_volatility` | no | $-120.78 | $-208.78 | $+471.16 | $+795.06 |
| `long_only` | no | $+56.04 | $-332.72 | $+640.20 | $+1020.58 |
| `low_volatility` | no | $+215.80 | $+54.00 | $-54.48 | $+17.88 |
| `mid_volatility` | no | $-17.28 | $-351.38 | $-5.90 | $-67.30 |
| `mostly_live_depth` | no | $+0.00 | $+0.00 | $+136.14 | $+509.60 |
| `mostly_replay_depth` | no | $+219.44 | $-528.84 | $+310.24 | $+336.00 |
| `overnight_only` | no | $+316.82 | $-374.18 | $+529.80 | $+492.30 |
| `rth_only` | no | $-97.38 | $-154.66 | $-83.42 | $+353.30 |
| `short_only` | no | $+163.40 | $-196.12 | $-193.82 | $-174.98 |

## Retrospective Change Point

- Best post-hoc split: `2026-05-18T23:21:00+00:00` / trading day `2026-05-19`.
- Before: 134 trades, $-322.82, $-2.41/trade.
- After: 95 trades, $+1305.40, $+13.74/trade.
- Multiple-split-adjusted permutation p-value: 0.2274.
- This split was discovered using all outcomes and cannot be used as a trading rule.

## Verdict

**No tested regime rule was knowable and profitable across both development halves.** The later long/high-volatility strength is a real observed shift, but using it now as a filter would be post-hoc.

The correct next gate is prospective data after June 12, 2026, when this diagnosis and gate were frozen. Freeze the formula and diagnostics; do not tune a long/high-volatility filter on the validation/final blocks.

Supporting files: `period_summary.csv`, `feature_drift.csv`, `outcome_association.csv`, `cohort_stability.csv`, `predefined_rule_audit.csv`, and `change_point_audit.json`.
