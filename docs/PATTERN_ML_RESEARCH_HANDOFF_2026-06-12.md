# Pattern / ML Trading Research Handoff

Date: June 12, 2026

## Purpose

Start a separate research session on a more powerful machine to explore strategies
that are not limited to fixed indicator formulas:

1. historical analog / nearest-neighbor pattern matching;
2. supervised machine-learning filters and, later, independent ML signals;
3. sequence models only after simpler approaches establish a credible baseline;
4. LLM assistance only as a slow regime/supervisory layer, not as the direct order
   execution decision-maker.

This phase is research-only. It must not request brokerage credentials, connect to a
live account, or submit orders.

## June 13 Scope Update: IBKR Futures

Apex was the original motivation, but its evaluation and payout rules are no longer
the governing research objective. The active longer-term direction is automated or
systematic futures trading through IBKR after research and paper validation.

The first ML experiment below remains a useful narrow rejection test. It should not be
interpreted as a general rejection of ML for futures. The follow-up review identifies
the strongest missed direction as pooled, portfolio-level learning across many liquid
futures, with continuous positions, cross-sectional/cross-market features, and
after-cost portfolio validation.

See:

```text
reports/pattern_ml_20260612/IBKR_ML_RESEARCH_REVIEW.md
```

### First Multi-Futures Baseline Result

The first roll-safe evaluation on the Databento daily dataset is complete:

```text
reports/multi_futures_baseline_20260613/VERDICT.md
```

The lead research baseline is monthly-rebalanced cross-sectional momentum:

- `7.29%` CAGR and `0.57` Sharpe at a two-basis-point one-way turnover cost;
- `-30.36%` maximum drawdown;
- positive at five basis points one-way cost;
- positive in six of seven asset classes and all leave-one-market/year tests;
- monthly payoff ratio `1.23` and monthly profit factor `1.58`.

It is not approved for live trading or independently confirmed. The monthly rebalance
variant was selected after inspecting the same history, Databento daily bars are UTC
calendar buckets rather than exchange sessions, and simulated gross exposure reaches
`3.67x` before explicit IBKR margin constraints.

### Comprehensive Multi-Futures Evaluation

The expanded strategy lab evaluated `112` predefined variants across `11` families:
time-series and cross-sectional momentum, moving-average trend, breakouts, carry,
short-horizon reversal, combined signals, and universe-sensitivity tests.
This is a broad daily systematic-strategy screen, not yet a supervised-ML model
comparison or an exhaustive search of every possible strategy.

```text
reports/multi_futures_comprehensive_20260613/COMPREHENSIVE_EVALUATION.md
```

The principal result is a family-level finding rather than a single winning parameter:

- cross-sectional momentum is the only consistently interesting family;
- `18/20` cross-sectional momentum variants are positive over the complete period at
  two basis points one-way cost;
- the clean all-market `xsec_cont_252_monthly` variant has `7.46%` CAGR, `0.58`
  Sharpe, and `-30.36%` maximum drawdown over the complete period;
- the stronger `xsec_cont_252_monthly_core_liquid` result has `9.29%` CAGR, `0.79`
  Sharpe, and `-19.93%` maximum drawdown, but its universe was informed by prior
  inspection and is therefore a post-hoc hypothesis;
- carry fails out of sample, and recent short-horizon reversal strength is not stable
  across earlier periods;
- `12/112` variants pass the conservative period, cost, drawdown, profit-factor, and
  exposure screen.

The search-wide block-bootstrap audit does **not** reject the multiple-testing null:
the observed best development Sharpe is `0.80`, the null 95th percentile is `1.01`,
and the family-wise p-value is `0.2134`. No tested strategy is statistically proven or
approved for live trading.

The next validation target is the cross-sectional momentum family. Preserve
`xsec_cont_252_monthly` as the clean benchmark and treat the core-liquid/no-agriculture
variants as hypotheses requiring genuinely unseen data. Before IBKR paper deployment,
rebuild the daily data into exchange sessions and add explicit contract selection,
notional sizing, margin, commissions, and roll execution.

### `$1,000-$2,000` IBKR Capital Constraint

The integer-contract and margin feasibility study is complete:

```text
reports/ibkr_small_account_20260613/VERDICT.md
```

The capital constraint changes the practical verdict:

- the diversified cross-sectional momentum portfolio cannot currently be replicated
  with `$1,000`, `$1,500`, or `$2,000`;
- faithful integer replication places zero trades from July 2025 onward because even
  the smallest current contract notionals are too coarse for the target weights;
- concentrated one-contract adaptations are different strategies and produced roughly
  `78%-93%` losses in the conservative full-history tests;
- the superficially positive synthetic replication history depends mainly on
  hypothetical `QNDX` use at older index levels, including before the product existed;
- current initial margin affordability alone is not sufficient: a single daily move
  can still consume a large share of the account.

Do not move the daily diversified momentum strategy to IBKR paper simulation at this
capital level. Continue research on strategies explicitly designed for one very small
contract, or use non-futures instruments that permit genuinely fractional sizing.

### MNQ At IBKR

MNQ does not solve the `$1,000-$2,000` IBKR capital constraint:

```text
reports/mnq_ibkr_capital_20260613/VERDICT.md
```

As of June 13, 2026, IBKR publishes approximately `$4,877` intraday initial margin and
`$6,967` overnight long initial margin for one MNQ contract. The account therefore
cannot open one MNQ contract at IBKR. The existing MNQ `vwap_delta_rejection`
candidate has mechanically modest modeled stop losses relative to margin, but only
about two months of searched history and no independent prospective confirmation.
Continue MNQ paper research and the frozen prospective monitor; do not fund a live MNQ
account with `$1,000-$2,000`.

The separate exact-`$5,000` intraday path test is:

```text
reports/mnq_5000_intraday_20260613/VERDICT.md
```

`$5,000` is technically above current intraday initial margin, but leaves only about
`$123` of entry buffer. In the historical RTH-only sequence, it takes 14 of 42 signals,
then falls below initial margin and cannot re-enter. The researched formula is mostly
overnight, for which `$5,000` is not eligible. Historical arithmetic suggests roughly
`$5,500-$6,000` for a more resilient RTH-only paper test and approximately `$7,736`
for overnight initial margin plus the observed candidate drawdown. These are research
reference points, not live-trading approvals or defensible worst-case capital estimates.

For a `$6,000` account specifically, see:

```text
reports/mnq_5000_intraday_20260613/SIX_THOUSAND_VERDICT.md
```

It is sufficient for the current one-contract RTH-only paper-test path, leaving
approximately `$1,123` above current intraday initial margin at funding. All 42
historical RTH signals remain executable with a minimum observed equity of about
`$5,680`, but their net PnL is only about `$60` and profit factor is `1.08`. The
account is still below overnight initial margin and the formula's existing history is
mostly overnight. A 15% margin increase would also violate the proposed `$250` entry
reserve during the observed path.

For a `$10,000` one-contract MNQ overnight-capable paper account, see:

```text
reports/mnq_10000_overnight_20260613/VERDICT.md
```

At current published IBKR margins, `$10,000` leaves approximately `$3,033` above the
overnight long initial requirement. After enforcing one open position at a time, all
228 historical candidate trades remain executable with a `$1,000` entry reserve:
186 are overnight-session trades and 42 are RTH. The adjusted result is approximately
`+$1,371`, profit factor `1.38`, payoff ratio `1.62`, and maximum drawdown `$803`.
Trade-order permutations show no margin skips at `$10,000` with the `$1,000` reserve.
A 20% margin increase remains executable in the observed path, while a 30% increase
causes many signals to be skipped. This supports `$10,000` as a sensible paper-test
capitalization, not as live-trading approval; the strategy still has only about two
months of searched history and requires genuinely prospective confirmation.

### Bias And History Validation Protocol

The frozen protocol is:

```text
MNQ_VALIDATION_PROTOCOL_2026-06-13.md
```

It controls selection bias by freezing the primary formula, costs, one-position rule,
and gates. Any change creates a new challenger with a new prospective clock. The
decision-grade target is at least 200 non-overlapping future trades, 60 substantial
days, two contract/roll periods, and trading-day bootstrap lower bounds above
break-even. A separate older-data MNQ/NQ replication request is preregistered before
download and must be run once without tuning. A pre-outcome dependency audit amended
the required request to MNQ `trades` only because the frozen formula explicitly does
not use depth; the current estimate is `$770.83` for 29.56 GB. NQ `trades` are an
optional, separately reported portability check. No historical replication download
has been started.

Important interpretation: freezing does not remove the bias created when
`vwap_delta_rejection` was chosen after the broad search. It only prevents further
adaptation while independent evidence is collected. The earlier `$4.98` Apex-era
reserve was removed before any prospective trades were observed. The June 13, 2026
IBKR model now uses approximately `$1.24` direct round-turn fees or `$2.24` including
one MNQ tick of slippage per side. The original analyzer rows could overlap, while the
frozen candidate permits one position at a time.

The strategy alternatives are retained locally in the analyzer source, 641-group
scorecard, and MNQ/NQ trade reports. See:

```text
reports/pattern_ml_20260612/SELECTION_BIAS_AND_IBKR_COST_REVIEW.md
```

The realistic `$2.24` IBKR-cost simulations and metadata-only free-credit purchase
assessment are complete:

```text
reports/pattern_ml_20260612/REALISTIC_COST_AND_FREE_CREDIT_ASSESSMENT.md
reports/mnq_10000_overnight_realistic_20260613/
reports/mnq_5000_intraday_realistic_20260613/
reports/pattern_ml_20260612/budget_constrained_replication_plan.json
```

At `$2.24`, the one-position overnight sample produces `$1,995.78`, profit factor
`1.62`, payoff ratio `1.86`, and `$557.18` maximum drawdown. These are still
selection-biased historical results. An earlier metadata-only `$120` plan proposed six
months of 2024 MNQ trades; it was superseded by the more recent 2025 Q1 package below.

### Recent Independent Replication Completed

The user approved the more recent 2025 Q1 package instead of the older 2024 plan. The
download completed for an actual `$91.55`:

```text
data/databento_2025q1_replication/
reports/pattern_ml_20260612/DATABENTO_2025Q1_DOWNLOAD_AND_PRIMARY_VERDICT.md
reports/mnq_2025q1_primary_replication/VERDICT.md
```

The primary-only test used 453 non-overlapping trades across 63 days and the `$2.24`
cost model. It lost `$679.22`, with profit factor `0.89`, expectancy `-$1.50`, payoff
ratio `1.51`, and maximum drawdown `$1,173.06`. Trading-day bootstrap lower bounds
failed. **Reject the frozen MNQ 1-minute `vwap_delta_rejection` primary.**

No alternative-strategy outcomes were generated in this primary-only run. The
downloaded MNQ/NQ one-minute bars may now be used for a separately registered
alternative-development exercise.

## Recommended Transfer Bundle

Use the `MNQ-NQ` profile from:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\Prepare-PatternMlResearchTransfer.ps1 `
  -Destination D:\transfer\trading-pattern-ml `
  -Profile MNQ-NQ
```

Replace `D:\transfer\trading-pattern-ml` with the intended USB drive, network share,
or other transfer directory.

After copying the prepared folder to the other machine, verify it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\Verify-PatternMlResearchTransfer.ps1
```

Why `MNQ-NQ`:

- MNQ is the practical target because one-contract risk and costs fit the current
  research objective.
- NQ is the most useful cross-instrument confirmation source.
- The compressed canonical data is approximately 539 MB:
  - MNQ: approximately 300.5 MB;
  - NQ: approximately 238.8 MB.
- Selected baseline reports add approximately 50 MB.

Other profiles:

- `MNQ`: approximately 300.5 MB canonical data; fastest initial pattern prototype.
- `Full`: approximately 1.0 GB canonical data for MNQ, NQ, ES, and MES.

The helper copies the current working files, including uncommitted research changes.
Do not use only `git clone`: much of the current implementation and documentation is
not committed.

## Data To Copy

The essential research data is:

```text
data\canonical_orderflow_1s\
  canonical_mnq_06-26_<YYYYMMDD>_1s.csv.gz
  canonical_nq_06-26_<YYYYMMDD>_1s.csv.gz
  manifest.json
```

Canonical version: **3**

Coverage:

| Instrument | Calendar range | Files | Nontrivial days | Canonical seconds |
|---|---:|---:|---:|---:|
| MNQ 06-26 | 2026-04-01 to 2026-06-08 | 65 | 49 | 3,747,654 |
| NQ 06-26 | 2026-04-01 to 2026-06-08 | 65 | 49 | 3,678,820 |
| ES 06-26 | 2026-04-01 to 2026-06-08 | 65 | 49 | 3,617,089 |
| MES 06-26 | 2026-04-01 to 2026-06-08 | 64 | 49 | 3,700,235 |

Each compressed CSV contains one row per usable second. Important fields include:

- trade count, volume, buy/sell volume, and trade OHLC;
- quote updates, bid/ask, sizes, and spread;
- depth snapshot counts, totals, and imbalance;
- the last recorded depth book for levels 0 through 9;
- separate trade, quote, and depth source provenance.

Read [CANONICAL_ORDERFLOW.md](CANONICAL_ORDERFLOW.md) before implementing a reader.

## Data Not To Copy

Do not copy these for the new pattern/ML research session:

- `C:\Users\vlast\Documents\NinjaTrader 8\export`: enormous raw/replay export archive.
- `reports\runtime\canonical_orderflow_shards`: approximately 1.15 GB and only needed
  to incrementally rebuild canonical data from raw exports.
- `reports\canonical_corrected_20260611\*_regime_trades.csv`: exhaustive generated
  reports totaling well over 1 GB and reproducible from canonical data.
- NinjaTrader replay databases, credentials, account configuration, or `.codex`
  session data.
- Root binaries such as `orderflow_analyzer.exe`; rebuild them on the new machine.

The canonical compressed files are the correct stable input for independent research.

## Code And Context Included By Transfer Helper

The helper includes:

- `src\orderflow_analyzer\`: existing Go strategy/backtest analyzer;
- `src\canonical_orderflow\`: canonical builder and schema behavior;
- `scripts\`: current analysis and supporting scripts;
- `ninjatrader\`: baseline strategy implementation and documentation;
- root Python research scripts and `go.mod`;
- current research documents;
- selected baseline reports from `reports\canonical_corrected_20260611`.

Selected baseline reports deliberately exclude giant exhaustive regime-trade files.
They include:

- `VERDICT.md` and `strategy_scorecard.md`;
- per-instrument `*_trades.csv`;
- day regimes and regime selectors;
- advisor sensitivity;
- regime filters;
- the human-readable analysis report.

## Current Research Verdict

No strategy is approved for unattended or real-money trading.

The current strongest formula candidate is:

**MNQ 1-minute `vwap_delta_rejection`**

- 236 simulated trades;
- +53.11R;
- approximately $2,019 simulated one-contract PnL;
- approximately $530 maximum drawdown;
- positive April, May, and June;
- still positive under one- and two-bar entry delays.

Its exact NinjaTrader implementation is currently being validated separately using
Playback with:

- `EnableOrders=False`;
- `SignalOnlyValidation=True`;
- `SimOnly=True`;
- account `Playback101`.

The separate pattern/ML research should not wait for or interfere with that replay.
Use the canonical dataset and corrected baseline reports as the research snapshot.

## Canonical Data Limitations

- Only about two months / 49 substantial sessions are available. This is enough to
  prototype and reject bad ideas, but not enough to prove a durable trading edge.
- Exact ordering of multiple events within one second is not preserved.
- Trade, quote, and depth components can come from different strongest recordings for
  the same second. Provenance columns expose this.
- Some weekend/empty-session files contain only one or a few rows. Exclude them.
- All current equity-index data is the June 2026 contract. Longer-history research
  will eventually need contract-roll handling.
- Depth can be noisy, transient, and spoof-like. Treat it as a feature, not truth.
- The previous June 10 conclusions were invalidated by a timezone defect. Use only
  canonical format version 3 or newer.

## Recommended Research Order

### 1. Build A Leak-Free Feature Dataset

Create features only from information available at decision time. Start with decisions
every minute or every five minutes; retain second-level inputs for window features.

Suggested normalized features:

- returns over 10s, 30s, 1m, 5m, 15m, and 60m;
- realized volatility and range in ATR units;
- distance from VWAP and recent highs/lows in ATR units;
- volume, trade-count, and delta ratios versus rolling history;
- spread level, spread volatility, and quote-update intensity;
- depth imbalance level, change, persistence, and book slope;
- depth additions/removals near the inside market;
- time of day and session bucket;
- MNQ/NQ divergence and confirmation;
- current formula-strategy setup flags as optional model features.

Do not begin with raw absolute price, raw depth size, or hundreds of unconstrained
features.

### 2. Define Explicit Outcomes

Prefer labels that map to executable trades:

- does +2R occur before -1R within a fixed horizon;
- future return after 5, 15, and 30 minutes after realistic costs;
- maximum favorable and adverse excursion;
- abstain/no-trade when neither outcome is meaningful.

Stops, targets, horizon, commission, spread, and slippage must be fixed before model
selection. Report both gross and net results.

### 3. Establish Baselines

Compare every complex approach against:

- no-trade;
- random entries matched by session/time distribution;
- simple logistic regression;
- current formula candidate;
- simple nearest-neighbor analog matching;
- gradient-boosted trees.

If a complex model cannot beat these out of sample, reject it.

### 4. Historical Analog Matching

For each decision point:

1. build a normalized feature vector for the preceding market window;
2. search only earlier historical windows;
3. exclude the same trading day and strongly overlapping windows;
4. inspect the distribution of what happened next;
5. trade only when enough neighbors agree and expected net value clears a threshold;
6. otherwise abstain.

Output the nearest historical examples for every proposed trade. Explainability is a
major advantage of this approach.

### 5. Supervised ML

Start with logistic regression and gradient-boosted trees. Initially use ML as a filter
for formula or pattern setups. Only test independent ML-generated entries after the
filter demonstrates stable out-of-sample improvement.

Calibrate probabilities. A score of `0.70` is not useful unless events scored near
`0.70` actually succeed near 70% of the time.

### 6. LLM / AI Experiments

Do not use an LLM as a direct high-frequency order-flow predictor. It is poorly suited
to dense numerical time series, difficult to backtest deterministically, and introduces
latency and model-version risk.

Potentially useful later:

- classify a slow market regime from a compact structured summary;
- identify abnormal/out-of-distribution conditions;
- choose among already validated strategy profiles;
- explain trades and research results.

Any LLM output must be constrained to a small predefined action set and must never
control order size, safety limits, or submit orders directly.

## Mandatory Validation Rules

- Never use random train/test row splitting.
- Use anchored walk-forward validation.
- Keep the final date block untouched until model and thresholds are frozen.
- Purge overlapping samples around split boundaries by at least the label horizon.
- Fit scalers, feature selectors, and models using training data only.
- During nearest-neighbor search, use only records earlier than the query timestamp.
- Exclude the same day and nearby overlapping windows from analog neighbors.
- Include commissions, spread, slippage, and delayed/missed execution.
- Report results by month, session, long/short, and volatility regime.
- Reject models whose profits depend on a few trades or one narrow period.
- Track every experiment configuration and output deterministically.

A reasonable first split for prototyping is:

- development: April through May 15;
- validation: May 18 through May 22;
- untouched final test: May 25 through June 5.

After choosing a design, replace this single split with anchored walk-forward folds.

## Expected First Deliverables

1. A canonical-second reader with data-quality and provenance filtering.
2. A minute/5-minute decision-point feature table.
3. A deterministic label table with MFE, MAE, target-before-stop, and costs.
4. A nearest-neighbor analog baseline with example-neighbor explanations.
5. Logistic-regression and boosted-tree baselines.
6. Walk-forward comparison against `vwap_delta_rejection` and no-trade/random controls.
7. A concise verdict identifying:
   - out-of-sample expectancy;
   - drawdown;
   - calibration;
   - stability by period and regime;
   - whether the model adds value beyond existing formula signals.

## Suggested Environment

- Python 3.11 or newer;
- Go 1.22 or newer;
- sufficient RAM to process several million second rows;
- start with `polars`, `numpy`, `scikit-learn`, `pyarrow`, and `joblib`;
- add LightGBM/XGBoost only after the basic leak-free pipeline works;
- use GPU sequence models only after simpler baselines are credible.

## Bootstrap Prompt For The New Codex Session

Paste this into a new Codex session started in the transferred folder:

```text
Read AGENTS.md, PATTERN_ML_RESEARCH_HANDOFF_2026-06-12.md,
CANONICAL_ORDERFLOW.md, and reports/canonical_corrected_20260611/VERDICT.md.

This is a research-only session. Do not connect to brokers, request credentials,
modify NinjaTrader, or place orders.

Goal: implement a leak-free historical-analog and supervised-ML research pipeline
for MNQ using the compressed canonical second-level dataset, with NQ as optional
cross-instrument confirmation. Begin by inventorying the transferred data and
verifying canonical manifest/version/coverage. Then implement deterministic
decision-point features and target-before-stop/MFE/MAE labels. Establish random,
formula, logistic-regression, nearest-neighbor, and boosted-tree baselines using
anchored walk-forward validation and realistic costs. Keep May 25 through June 5
untouched as the first final test block. Produce reproducible reports and explicitly
audit leakage, overlap, calibration, drawdown, and period concentration.
```

## Existing Files Worth Reading First

- [CANONICAL_ORDERFLOW.md](CANONICAL_ORDERFLOW.md)
- [ORDERFLOW_ANALYZER.md](ORDERFLOW_ANALYZER.md)
- [reports/canonical_corrected_20260611/VERDICT.md](reports/canonical_corrected_20260611/VERDICT.md)
- [scripts/advanced_context_lab.py](scripts/advanced_context_lab.py)
- [scripts/cross_instrument_confirmation.py](scripts/cross_instrument_confirmation.py)
- [src/orderflow_analyzer/canonical.go](src/orderflow_analyzer/canonical.go)
- [src/orderflow_analyzer/signals.go](src/orderflow_analyzer/signals.go)
- [ninjatrader/OrderFlowResearchStrategy.cs](ninjatrader/OrderFlowResearchStrategy.cs)
