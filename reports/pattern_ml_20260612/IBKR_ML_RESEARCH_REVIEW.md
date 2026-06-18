# IBKR Futures ML Research Review

Date: June 13, 2026

## Revised Verdict

Yes, the prior research missed a genuinely interesting ML direction.

The current experiment asks a narrow question: every five minutes on MNQ/NQ, can a
classifier predict whether a fixed `+2R` target occurs before a fixed `-1R` stop during
the next 30 minutes? It then uses the prediction as an entry/no-entry decision.

That is a valid rejection experiment, but it is not where the strongest academic
evidence for ML in futures lies. The more promising direction is:

**pool many liquid futures over long histories, learn a continuous position or
cross-sectional ranking from multi-horizon trend, carry, volatility, and cross-market
information, and evaluate the resulting portfolio after turnover and costs.**

This changes both the target and the source of statistical power. It aligns better
with the actual objective: favorable expected gains relative to losses, not maximum
classification accuracy or avoidance of losing trades.

The first implementation should still be conservative. A pooled ridge/LASSO or
gradient-boosting model should be the baseline. Deep Momentum Network or Momentum
Transformer-style models become justified only after the broad, long-history dataset
and simple portfolio baselines exist.

## What The Existing Experiment Actually Tested

The current `pattern_ml_research.py` experiment:

- uses approximately 49 substantial sessions from one June 2026 contract;
- focuses on MNQ and NQ, which are the same underlying exposure at different sizes;
- samples decisions every five minutes;
- fixes one 30-minute holding horizon and one `+2R/-1R` barrier outcome;
- predicts a binary `target_before_stop` label;
- tests historical analogs, logistic regression, and histogram gradient boosting;
- uses hand-engineered price and order-flow summaries;
- converts the score into a trade/no-trade threshold.

It does **not** learn:

- the expected size or distribution of future returns;
- maximum favorable and adverse excursion jointly;
- the best holding horizon or exit policy;
- a continuous position size;
- portfolio allocation or diversification;
- cross-sectional relative value;
- term structure, carry, basis, or contract-roll information;
- sparse lead-lag relationships across economically distinct futures;
- sequence representations from full order-book histories.

The negative classifier result therefore rejects these particular labels, features,
and decision rules. It does not reject ML for futures generally.

## Where Academic Evidence Is Most Interesting

### 1. Direct Position And Portfolio Learning

This is the strongest missed direction.

Deep Momentum Networks were tested on 88 continuous futures. The important finding is
not merely that an LSTM was used. Models that directly generated position sizes and
optimized portfolio Sharpe outperformed ordinary regression and binary classification.
Volatility scaling, direct position outputs, and portfolio-level optimization were
central to the reported gains. The paper also found that greater architectural
complexity did not automatically improve performance. Its ML models traded much more
than simple benchmarks, and the best LSTM retained its advantage only up to roughly
`2-3` basis points of transaction costs.

The Momentum Transformer extends this idea with attention over multiple timescales.
It reports improved net-of-cost performance and adaptation around changing regimes.
This is worth reproducing only after establishing simple multi-market baselines.

Why it matters here:

- It optimizes the economics of gains and losses instead of classification accuracy.
- Continuous exposure can express weak but persistent signals.
- Diversification supplies many more independent observations than MNQ/NQ alone.
- The model can reduce or reverse exposure rather than force every decision into a
  fixed stop/target trade.

### 2. Cross-Sectional Ranking And Sparse Cross-Market Lead-Lag

This was absent from the current research and may be more practical than deep learning.

Recent commodity-futures research finds that cross-sectional models based on momentum,
basis, and basis-momentum produce better forecasts than historical-average and
time-series forecasting alternatives. Another futures study used nearly ten years of
minute data across 60 futures and reported statistically significant out-of-sample
break-even transaction costs for a cross-sectional top/bottom ranking strategy.

Research on commodity lead-lag relationships is especially useful as a warning against
unnecessary complexity: sparse LASSO forecasts produced economically meaningful
out-of-sample gains, while regression trees and neural networks performed worse.

For this project, an initial universe could include equity indexes, rates, currencies,
energy, metals, and selected agricultural futures. Useful questions include:

- Do rates, USD, volatility, or energy moves lead NQ at daily or hourly horizons?
- Can a pooled model rank markets by expected risk-adjusted return?
- Do curve slope, carry, open interest, or basis improve the ranking?
- Are the selected relationships stable across walk-forward periods and contract rolls?

### 3. Volatility, Quantiles, And Uncertainty Instead Of Direction

Return direction is extremely noisy. Volatility and risk are more persistent and can
still improve trading economics.

Research on multi-asset intraday volatility shows that pooling assets and using common
market volatility can materially improve out-of-sample forecasts. A useful model here
could predict:

- future realized volatility at several horizons;
- return quantiles rather than a binary direction;
- expected maximum favorable and adverse excursion;
- probability that costs consume the expected move;
- uncertainty or out-of-distribution scores.

Those outputs can control exposure, choose among horizons, or abstain. This directly
supports a better winner/loss distribution without pretending that every entry
direction is predictable.

### 4. Pooled Order-Book And Microstructure Learning

There is credible evidence that order-flow and order-book relationships can generalize
across instruments. Research using billions of quotes and trades found that pooled
models could learn price-formation features that generalized to unseen stocks.
Microstructure research across 87 liquid futures also found out-of-sample predictive
information and important cross-asset effects.

This is genuinely interesting, but it is not ready for the current canonical data:

- only about 49 substantial sessions are available;
- event ordering within a second is not retained;
- depth is throttled and may have mixed source provenance;
- MNQ and NQ do not provide meaningful cross-asset diversity.

A future version should record full, consistently sourced depth and trades across
multiple futures. A simple pooled microstructure model should precede DeepLOB-style
sequence models.

### 5. Online Changepoint Detection Around A Robust Base Strategy

Regime adaptation is useful when it is designed prospectively rather than inferred
after a profitable period appears. Peer-reviewed work combining online changepoint
detection with a deep momentum model reports improved response around trend reversals.

This does not justify adding another retrospective regime filter to the current MNQ
formula. It is a later extension for a broad, already-credible momentum portfolio.

## Public Practitioner Experience

Public experience is much more skeptical than the most attractive papers, and that
skepticism is useful.

Common practitioner themes are:

- Problem definition, data quality, and leakage control matter more than the model
  family.
- Simple linear or tree models are difficult to beat after realistic costs.
- Sophisticated architectures often make small improvements, if any, and increase the
  opportunity for overfitting.
- A model is more useful when it sizes, ranks, forecasts risk, or filters a known edge
  than when it tries to discover profitable direction from generic indicators.
- Meta-labeling is not a magic source of information. If the secondary model receives
  the same information as the first, it may simply repackage the same weak signal.

Public discussions are anecdotes, not validation. Their value is that they describe
the same failure modes seen in the current experiment: attractive training behavior,
unstable thresholds, and failure when the regime changes.

## Critical Assessment Of The Academic Results

The academic results are promising research priors, not evidence that an IBKR retail
implementation will earn money.

Important caveats:

- Papers benefit from large, cleaned datasets and often simplified execution models.
- Published results are selected from a much larger unpublished research population.
- Much of the underlying edge may come from established momentum, carry, volatility,
  and diversification effects; ML may add only an incremental improvement.
- Futures continuation, roll timing, point values, margin, and transaction costs can
  materially change results.
- Reported statistical predictability may be too small to trade at a retail cost level.
- Deep models introduce many researcher degrees of freedom and should face stronger
  evidence thresholds than simple models.
- A broad portfolio can look robust while depending on a few markets, eras, or crisis
  periods.

The correct response is not to dismiss the work. It is to reproduce its core economic
ideas with simpler models, strict walk-forward validation, and a fully executable
portfolio simulation.

## Ranked Research Directions

| Rank | Direction | Assessment | Current readiness |
|---:|---|---|---|
| 1 | Multi-futures trend/carry model with continuous volatility-scaled positions | Best combination of evidence, diversification, and alignment with payoff objective | Needs long-history multi-market data |
| 2 | Cross-sectional ranking and sparse cross-market lead-lag | Strong evidence that simple sparse models can beat complex ones | Needs broader universe, curves, and rolls |
| 3 | Volatility/quantile/MFE-MAE forecasting for sizing and horizon selection | More predictable target and useful even with weak direction forecasts | Can prototype after broader data exists |
| 4 | Pooled microstructure model across distinct futures | Academically interesting and relevant to existing order-flow work | Requires much more consistent tick/depth data |
| 5 | Online changepoint adaptation for a validated trend portfolio | Plausible way to reduce reversal losses | Defer until a robust base portfolio exists |

Do not prioritize:

- more classifiers on the same `target_before_stop` dataset;
- LSTM or Transformer training on 49 NQ/MNQ sessions;
- reinforcement learning for entry and exit;
- LLM-directed trading;
- post-hoc regime filters;
- DeepLOB on the current throttled canonical depth data.

## Recommended Next Experiment

Build a separate **multi-futures portfolio research lane**. Keep the current NQ
order-flow work as an independent intraday lane.

### Dataset

- At least 15-30 liquid futures across equity indexes, rates, FX, energy, metals, and
  selected agriculture.
- Prefer 10 or more years of daily data; add hourly data only after the daily pipeline
  is correct.
- Store individual contracts and explicit roll decisions. Do not rely blindly on a
  vendor-adjusted continuous series.
- Add front/next contract prices, curve slope, carry/basis, volume, and open interest
  where available.

### Features

- volatility-normalized returns over several horizons;
- moving-average and breakout trend measures;
- realized volatility and downside volatility;
- carry, basis, curve slope, and basis-momentum;
- open-interest and volume changes;
- cross-market lagged returns and volatility;
- calendar and session effects.

### Targets And Outputs

- future excess returns at several horizons;
- future realized volatility and return quantiles;
- continuous target exposure in `[-1, 1]`;
- cross-sectional score or rank;
- optional uncertainty/abstain score.

### Baselines

1. Equal-risk time-series momentum.
2. Cross-sectional momentum and carry.
3. Ridge, LASSO, and Elastic Net.
4. Gradient-boosted trees.
5. Only then, a small direct-position neural model.

Every model should be compared after the same volatility target, turnover limit,
contract-roll process, commissions, spread/slippage assumptions, and portfolio risk
constraints.

### Validation

- anchored walk-forward splits by date;
- untouched final years, not random rows;
- results by market, asset class, year, and regime;
- performance after removing the best market and best year;
- turnover and break-even-cost analysis;
- explicit trial count and multiple-testing adjustment;
- paper trading through IBKR before any live use.

## IBKR-Specific Implications

IBKR is a reasonable execution and forward-data platform for this direction because it
provides access to many futures markets through one API. It should not automatically be
treated as the sole historical research database.

Official IBKR documentation notes:

- most API market data requires the relevant Level 1 subscription;
- market depth requires Level 2 data;
- historical data depends on subscriptions and API limitations;
- continuous futures represent the front future, and earlier history may require
  requesting direct dated contracts.

The practical design is therefore:

1. obtain or construct a contract-aware long-history research dataset;
2. use IBKR to record forward data and paper-execute frozen models;
3. keep research, signal generation, risk controls, and order execution as separate
   components.

## Bottom Line

The existing negative ML result is useful, but its scope is much narrower than the
phrase "ML-based futures strategy" suggests.

The genuinely interesting missed idea is **portfolio-level, pooled learning across
many futures, with continuous positions and targets tied to returns, volatility,
turnover, and payoff distribution**. Cross-sectional ranking and sparse lead-lag
models are the most practical first implementations. Deep sequence models are a later
benchmark, not the starting point. The likely durable advantage, if one exists, will
come more from the economic structure, breadth, and risk formulation than from choosing
a fashionable model.

## Sources

Academic and professional:

- Lim, Zohren, and Roberts, [Enhancing Time Series Momentum Strategies Using Deep Neural Networks](https://arxiv.org/abs/1904.04912)
- Wood et al., [Trading with the Momentum Transformer](https://arxiv.org/abs/2112.08534)
- Wood, Roberts, and Zohren, [Slow Momentum with Fast Reversion](https://ora.ox.ac.uk/objects/uuid:b3a07fa5-b249-4b0b-894d-7545252ca258)
- Han and Kong, [The Lead-lag Relations in Commodity Futures Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3536046)
- Angelidis, Sakkas, and Tessaromatis, [Predicting Commodity Returns: Time Series vs. Cross Sectional Prediction Models](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5205084)
- Schnaubelt, Fischer, and Krauss, [Machine Learning in Futures Markets](https://www.mdpi.com/1911-8074/14/3/119)
- Easley et al., [Microstructure in the Machine Age](https://academic.oup.com/rfs/article-abstract/34/7/3316/5868424)
- Sirignano and Cont, [Universal Features of Price Formation in Financial Markets](https://arxiv.org/abs/1803.06917)
- Zhang et al., [Volatility Forecasting with Machine Learning and Intraday Commonality](https://academic.oup.com/jfec/article/22/2/492/7081291)
- CFA Institute, [Machine Learning in Commodity Futures](https://rpc.cfainstitute.org/research/foundation/2025/chapter-8-machine-learning-commodity-futures)

Public practitioner sentiment, treated as anecdotal:

- Reddit r/algotrading, [Using Machine Learning for Trading in 2025](https://www.reddit.com/r/algotrading/comments/1kgqcs7/using_machine_learning_for_trading_in_2025/)
- QuantConnect, [Why Meta-Labeling Is Not a Silver Bullet](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)

IBKR documentation:

- [Market Data Subscriptions](https://www.interactivebrokers.com/campus/ibkr-api-page/market-data-subscriptions/)
- [Python API: Requesting Market Data](https://www.interactivebrokers.com/campus/trading-lessons/python-receiving-market-data/)
- [TWS API Documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/trader-workstation-api/)
