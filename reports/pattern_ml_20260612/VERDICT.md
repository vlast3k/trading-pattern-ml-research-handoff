# Pattern / ML Research Verdict

Research-only first pass generated from canonical format version 3. No broker connection or order submission was used.

## June 13 IBKR Direction Update

The Apex objective is no longer the governing research target. The IBKR-focused review
in `IBKR_ML_RESEARCH_REVIEW.md` finds that this experiment framed ML too narrowly as a
binary filter for fixed NQ/MNQ trades.

**Active recommendation:** keep this negative classifier result, but start a separate
multi-futures research lane using long contract-aware histories, cross-sectional and
cross-market features, continuous volatility-scaled positions, and portfolio-level
after-cost validation. Begin with ridge/LASSO and simple trend/carry baselines before
testing direct-position neural models.

## Fixed Design

- Decisions: every 5 minutes from trailing one-minute features.
- Entry: next one-minute bar open; horizon: 30 minutes.
- Outcome: +2R target before -1R stop; same-bar ties are stops.
- Costs: $3.98 commission plus 1 tick per side ($4.98 total fixed cost).
- Development thresholds: chosen only from anchored walk-forward out-of-fold predictions.
- Final test: May 25 through June 5, untouched until thresholds were frozen.

## Final Test

| Model | Frozen threshold | Trades | Target rate | Net PnL | Max DD | Days + / - | Best trade share |
|---|---:|---:|---:|---:|---:|---:|---:|
| `formula_vwap_delta_rejection` |  | 80 | 50.0% | $+845.60 | $208.34 | 7 / 3 | 11.8% |
| `analog` | 1.100 | 0 | 0.0% | $+0.00 | $0.00 | 0 / 0 | 0.0% |
| `gradient_boosted_trees` | 1.100 | 0 | 0.0% | $+0.00 | $0.00 | 0 / 0 | 0.0% |
| `logistic` | 1.100 | 0 | 0.0% | $+0.00 | $0.00 | 0 / 0 | 0.0% |

## ML Filter Of Formula Candidate

Filters are trained only on exact historical `vwap_delta_rejection` trades. A filter is frozen only if it improves total development walk-forward net PnL over keeping every formula trade.

| Model | Development action | Best development delta | Validation delta | Final delta | Final kept |
|---|---|---:|---:|---:|---:|
| `logistic` | filter | $+522.54 | $-161.74 | $-602.14 | 48/80 |
| `analog` | filter | $+372.30 | $-446.38 | $-707.32 | 14/80 |
| `gradient_boosted_trees` | filter | $+216.46 | $-329.72 | $-85.58 | 51/80 |

## Development Threshold Selection

| Model | Best tested threshold | Trades | Net PnL | Max DD | Frozen action |
|---|---:|---:|---:|---:|---|
| `logistic` | 0.500 | 15 | $-16.59 | $124.37 | no_trade |
| `gradient_boosted_trees` | 0.500 | 30 | $-33.22 | $201.98 | no_trade |
| `analog` | 0.600 | 27 | $-391.53 | $468.02 | no_trade |

## Validation Check

| Model | Trades | Net PnL | Max DD |
|---|---:|---:|---:|
| `formula_vwap_delta_rejection` | 19 | $+446.38 | $108.46 |
| `analog` | 0 | $+0.00 | $0.00 |
| `gradient_boosted_trees` | 0 | $+0.00 | $0.00 |
| `logistic` | 0 | $+0.00 | $0.00 |

## Random Controls

Random entries match each model's final-test direction and session-bucket counts over 100 deterministic repetitions.

| Model | Random mean | Random median | Positive repetitions | Random 95th percentile |
|---|---:|---:|---:|---:|
| `analog` | $+0.00 | $+0.00 | 0.0% | $+0.00 |
| `gradient_boosted_trees` | $+0.00 | $+0.00 | 0.0% | $+0.00 |
| `logistic` | $+0.00 | $+0.00 | 0.0% | $+0.00 |

## Calibration

| Period | Model | Brier score |
|---|---|---:|
| development_oof | `analog` | 0.2279 |
| development_oof | `gradient_boosted_trees` | 0.2204 |
| development_oof | `logistic` | 0.2192 |
| final_test | `analog` | 0.1901 |
| final_test | `gradient_boosted_trees` | 0.1697 |
| final_test | `logistic` | 0.1861 |
| validation | `analog` | 0.1984 |
| validation | `gradient_boosted_trees` | 0.1952 |
| validation | `logistic` | 0.2077 |

## Interpretation

This is a prototype/rejection dataset, not proof of a durable edge. Two months of one contract, one expiry, and second-level event ordering limitations remain material.

**Verdict: reject these first independent ML entry baselines for promotion.** None produced positive net final-test PnL after frozen selection and realistic fixed costs.

**Formula-filter verdict: no tested ML filter adds value beyond keeping all formula signals.**

## Regime-Shift Diagnosis

The formula's later strength was audited separately in `regime_shift/VERDICT.md`.

- Best post-hoc breakpoint: May 19, 2026.
- The breakpoint is not statistically convincing after adjusting for searching many splits (`p=0.2274`).
- Later profits are mainly long/high-volatility trades, but those rules lost money in development.
- A major replay-to-live provenance shift is a serious confounder.
- No predefined regime rule was profitable across both development halves after removing its best day.

Do not tune a long/high-volatility or live-data filter from the validation/final blocks. Because this gate was frozen on June 12, 2026, the next valid gate is data collected after June 12, 2026; the already-visible June 8 result is retrospective.

## Payoff-Asymmetry Review

The objective is favorable winner/loss size and profit factor, not avoiding all losses. The separate `payoff_asymmetry/VERDICT.md` review finds:

- Final test: average winner / average loser `1.56`, profit factor `1.73`, and `+$10.57` expectancy per trade before added slippage.
- With one tick of slippage per side: final-test payoff ratio `1.48`, profit factor `1.64`, and `+$9.57` expectancy per trade.
- Late development fails decisively: payoff ratio `1.19`, profit factor `0.68`, and `-$6.37` expectancy per trade.
- Only `51.0%` of rolling 30-trade windows have profit factor at least `1.20`; `51.5%` remain profitable after removing their largest winner.
- Final-test profit is concentrated in longs; final-test shorts lose money.

The recent block demonstrates the desired payoff shape, but history does not yet show that it is stable. Keep the exact unfiltered formula frozen and require the prospective payoff gate before promotion.

## Critical Review Update

The June 13 critical review in `CRITICAL_REVIEW_PUBLIC_SENTIMENT.md` supersedes any interpretation that the formula passed an independent final confirmation:

- The formula was selected after the broader corrected-canonical search inspected hundreds of strategy groups, so its "final test" is not a pristine formula holdout.
- The payoff report double-counts part of formula cost because the source `r` already embeds a `$2.00` round-turn cost. Correct reconstruction strengthens the formula metrics but does not repair selection bias or regime instability.
- The all-period corrected-cost result has profit factor `1.33`, but its trading-day block-bootstrap 95% interval includes `1.0`.
- With corrected `$3.98` commission plus one tick per side, the best observed 30-calendar-day result remains below the Apex 25K EOD `$1,500` evaluation target.

**Revised formula verdict: promising hypothesis, not independently validated, and not yet demonstrated to fit the Apex monetization objective.**

The exact existing `vwap_delta_rejection` formula rows are included as a contextual baseline. They use the existing analyzer's trade timing and can overlap, so they are not mechanically identical to the non-overlapping model selections.

For the current IBKR-oriented research verdict and ranked next experiments, see
`IBKR_ML_RESEARCH_REVIEW.md`.

See `config.json`, `model_summary.csv`, `calibration.csv`, `selected_trades.csv`, and `analog_neighbors.csv`, `performance_breakdowns.csv`, and `leakage_audit.json` for the reproducible audit trail.
