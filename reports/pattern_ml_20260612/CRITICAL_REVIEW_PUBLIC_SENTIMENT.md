# Critical Review And Public Sentiment

Date: June 13, 2026

## Revised Verdict

The objective is sound: a strategy does not need a high win rate if average winners
materially exceed average losers and the resulting expectancy survives costs, losing
streaks, and regime changes.

The current evidence does **not** independently validate `vwap_delta_rejection`.
Treat it as a plausible research hypothesis that deserves frozen prospective testing,
not as a strategy that has passed an out-of-sample confirmation.

## Most Important Problems

### 1. The Formula "Final Test" Is Not A Pristine Formula Holdout

The ML thresholds respected the May 25 through June 5 final block. The formula itself
did not originate inside that frozen experiment. It was already selected as the
strongest candidate after the corrected canonical scorecard inspected 641 strategy
groups and the transferred MNQ/NQ trade files contained 318 unique
instrument/timeframe/variant combinations.

Consequently, the formula's attractive final block is useful evidence, but its
confidence interval does not correct for winner selection across the broader research
search. This is the largest reason to downgrade the assessment.

### 2. The Cost Labels In The Payoff Report Are Wrong

The canonical trade CSV's `r` already embeds a `$2.00` round-turn cost. The ML loader
then labels that result as gross PnL and subtracts another `$3.98`. The payoff review's
"one tick per side" row subtracts another `$1.00`.

Therefore, the reported one-tick result charges approximately `$6.98` per trade, not
the stated `$4.98`. This is conservative rather than optimistic, but it makes the
reported metrics and Apex comparison internally inconsistent.

The root formula final-test table similarly charges approximately `$5.98` per trade
while describing a `$4.98` fixed cost.

Reconstructing raw PnL from entry and exit, then applying exactly `$3.98` commission
plus one MNQ tick per side produces:

| Period | Trades | Payoff ratio | Profit factor | Expectancy | Net PnL | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Early development | 47 | 1.86 | 1.38 | $+5.67 | $+266.44 | $208.06 |
| Late development | 83 | 1.27 | 0.72 | $-5.37 | $-445.84 | $676.02 |
| Validation | 19 | 1.55 | 2.66 | $+24.49 | $+465.38 | $106.46 |
| Final test | 80 | 1.65 | 1.82 | $+11.57 | $+925.60 | $200.34 |
| All reviewed periods | 229 | 1.60 | 1.33 | $+5.29 | $+1,211.58 | $769.64 |

Correcting costs strengthens the economics, but it does not repair selection bias or
late-development failure.

### 3. The Confidence Pass Is Too Strongly Worded

The payoff bootstrap resamples individual trades as independent observations. Trades
cluster by trading day, and seven reviewed signals enter before the preceding trade
exits. The overlap count is small, but daily clustering and common market regimes still
matter.

A trading-day block bootstrap using corrected costs gives the complete 51-day sample:

- Profit factor 95% interval: approximately `0.96` to `1.74`.
- Expectancy 95% interval: approximately `-$0.78` to `+$11.01` per trade.
- Estimated probability of positive expectancy: approximately `95.7%`.

The complete sample therefore does not clear a strict 95% positive-expectancy or
profit-factor-above-one standard. The selected final block does clear it, but contains
only ten days and is not a clean formula holdout.

The observed sequence also includes ten consecutive losing trades. That is compatible
with a positive-payoff strategy, but it is operationally important and should be part
of paper-trading and account-survival tests.

### 4. The Edge Is Direction And Regime Dependent

Across all 236 available formula trades with corrected realistic cost:

- Longs: `+$1,476.68`, profit factor `1.82`.
- Shorts: `-$160.96`, profit factor `0.92`.
- Late development: negative despite favorable average winner/loss size.
- The retrospective regime audit found no rule that was knowable and profitable
  across both development halves.

This means favorable payoff ratio alone is insufficient. The win probability fell too
far in late development, and recent long-side strength cannot be promoted into a
long-only filter without new independent evidence.

### 5. The Gate Is Not Yet Tied To The Actual Apex Objective

The current prospective gate checks 50 trades and 20 days, plus generic payoff and
drawdown thresholds. Those are useful research checks but do not directly answer:

- probability of passing an evaluation within 30 calendar days;
- probability of touching the EOD threshold or DLL using intratrade equity;
- probability and expected time to meet payout balance and qualifying-day rules;
- sensitivity to realistic missed fills and variable slippage.

Using all 236 available trades with corrected `$4.98` cost:

- Net PnL is `+$1,315.72`, below the 25K evaluation's `$1,500` target.
- Best 30-calendar-day PnL is approximately `+$1,409.70`, also below the target.
- Close-to-close max drawdown is approximately `$769.64` before a full intratrade
  threshold simulation.
- Eleven days exceed the 25K PA's `$100` qualifying-day threshold.
- Only one day exceeds the 50K PA's `$250` qualifying-day threshold.
- Best day is approximately `30.7%` of total profit, currently compatible with the
  50% consistency rule.

The strategy's distribution is not structurally incompatible with a 25K EOD account,
but the observed profit rate is too low to demonstrate reliable evaluation passing or
payout monetization.

The 50-trade/20-day prospective gate should therefore be treated as an interim
screening checkpoint. It is too short to establish robustness across contract rolls,
regimes, and changing execution conditions.

### 6. Formula Controls And Execution Comparison Are Incomplete

The random-control table tests only the independent ML models, which selected zero
final trades. It does not show whether the formula beats session- and
direction-matched random formula-frequency entries.

The formula and independent ML entries also use different trade mechanics. The formula
baseline uses the existing analyzer's signal-bar-close timing and can overlap; the ML
design enters at the next one-minute open and prohibits overlapping selected trades.
The report acknowledges this, but the headline table still invites an apples-to-apples
interpretation.

Exact NinjaTrader signal and fill matching, missed-fill sensitivity, and a matched
formula random control remain required.

## What The Public Sentiment Says

### Broad Practitioner Sentiment

Public algo-trading and futures discussions broadly agree on three ideas:

1. Win rate by itself is a vanity metric; expectancy combines win probability and
   win/loss magnitude.
2. Sub-50% win-rate strategies can be excellent when they have positive skew and a
   durable profit factor.
3. Low-win/high-payoff systems are psychologically and operationally difficult because
   they produce long losing streaks and depend on not missing relatively rare winners.

Recent public discussions commonly view roughly 45%-50% wins with about 2:1 reward/risk
as promising, but commenters consistently ask for more trades, realistic spread and
slippage, live-forward evidence, and drawdown analysis. These discussions are useful
for understanding practitioner concerns, but they are self-selected anecdotes rather
than validation evidence.

There is no credible universal public benchmark for a "good" profit factor. Retail
opinions often prefer `1.5` to `2.0+`, while this candidate's corrected full-sample
profit factor is `1.35`. That is positive but leaves limited room for degradation.

### Rigorous Research Sentiment

The academic and professional research consensus is more skeptical than retail
discussion:

- Backtest holdouts can remain unreliable after repeatedly trying strategies.
- The number of attempted trials is essential for judging whether the selected winner
  is meaningful.
- Selection bias, non-normal returns, costs, and regime instability require higher
  evidence thresholds than a conventional attractive backtest.

That consensus maps directly to this project because the formula was selected after a
large strategy search and its profitability changes sharply across adjacent periods.

### Prop-Account Sentiment And Rules

Prop-account discussion tends to favor smoother, repeatable daily returns because
drawdown and payout rules penalize concentrated outcomes. Apex's current official EOD
rules make that preference explicit:

- 25K evaluation: `$1,500` target, `$1,000` EOD drawdown, `$500` DLL, 30-day access.
- 25K PA payout: five days of at least `$100`, minimum balance `$26,600`, and no single
  profitable day at or above 50% of total profit since the prior payout.

Positive skew is still valuable, but a strategy must produce enough qualifying days
and avoid letting one large day dominate the payout cycle.

## Recommended Assessment Standard

Keep the candidate frozen and research-only, but replace "final confidence pass" with
"selected-block positive evidence."

Before another promotion review:

1. Correct the formula cost reconstruction and rerun all formula/filter reports.
2. Use trading-day or session-block bootstrap, not only independent-trade bootstrap.
3. Track the number of strategy/configuration trials and report PBO or a comparable
   multiple-testing correction.
4. Require new data from at least one additional contract/roll period and at least
   40 substantial prospective days.
5. Report direction-specific results with a numeric rule; do not let profitable longs
   silently subsidize persistently losing shorts.
6. Add a true Apex EOD simulation with corrected costs, variable slippage, missed fills,
   intratrade threshold checks, 30-calendar-day evaluation windows, and PA payout cycles.
7. Add formula-specific matched random controls and compare all candidates under the
   same executable entry and position-overlap rules.

## Sources

Rigorous research:

- Bailey et al., [The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- Bailey and Lopez de Prado, [The Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- Arnott, Harvey, and Markowitz, [A Backtesting Protocol in the Era of Machine Learning](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3275654)
- Harvey, Liu, and Zhu, [...and the Cross-Section of Expected Returns](https://www.nber.org/papers/w20592)

Current official Apex rules:

- [EOD Evaluations](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/)
- [EOD Performance Accounts](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-performance-accounts-pa/)
- [EOD Payouts](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/)
- [Daily Loss Limit Explained](https://apextraderfunding.com/help-center/additional-helpful-items/daily-loss-limit-explained/)

Public practitioner discussions, treated as sentiment rather than evidence:

- Reddit r/algotrading, [Sub 50% win ratio strategies](https://www.reddit.com/r/algotrading/comments/105se9a/sub_50_win_ratio_strategies/)
- Reddit r/algotrading, [What is generally a good expectancy and profit factor?](https://www.reddit.com/r/algotrading/comments/1sw2gyv/what_is_generally_a_good_expectancy_profit_factor/)
- Reddit r/FuturesTrading, [46% win rate at 1:2 R:R](https://www.reddit.com/r/FuturesTrading/comments/1q2vssn/46_win_rate_at_12_rr_worth_refining_further_or/)
- Reddit r/FuturesTrading, [Higher R:R with lower win rate, or lower R:R with higher win rate?](https://www.reddit.com/r/FuturesTrading/comments/1css8ep/higher_rr_with_lower_win_rate_or_lower_rr_with/)
