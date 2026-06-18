# MNQ Validation Protocol

Date frozen: June 13, 2026

## Purpose

Solve the two main evidence problems:

1. limited MNQ order-flow history;
2. selection bias from choosing `vwap_delta_rejection` after a broad strategy search.

Neither problem can be repaired by further tuning the existing April-June 2026 sample.
The solution is new independent evidence collected under rules frozen before outcomes
are observed.

## Frozen Primary Candidate

- Instrument: one MNQ contract.
- Formula: exact 1-minute `vwap_delta_rejection`.
- No long-only, session, volatility, provenance, ML, or discretionary filter.
- At most one open position; later overlapping signals are skipped.
- Modeled IBKR cost: `$1.24` round-turn fees plus one tick slippage per side,
  `$2.24` total.
- Prospective cutoff: after trading day June 12, 2026.

As checked on June 13, 2026, IBKR lists MNQ commissions of `$0.25` per contract, CME fee recovery of
`$0.35` per contract, and regulatory fee recovery of `$0.02` per contract. That is
approximately `$1.24` per round turn before slippage. One MNQ tick is `$0.50`, so one
tick per side produces an approximately `$2.24` broker-fee-plus-slippage baseline.
IBKR may also charge a separately modeled overnight position fee depending on excess
equity. Paper-account statements must replace estimates with observed costs. The
earlier `$4.98` Apex-era stress reserve was removed before any prospective trades were
observed.

The machine-readable registration is:

```text
reports/pattern_ml_20260612/prospective_monitor/candidate_registry.json
```

The original analyzer tournament could contain overlapping simulated trades. The
one-position rule was imposed later as an executable small-account constraint. It is
therefore a stricter frozen implementation of the selected formula, not a mechanically
identical reproduction of the original winning scorecard row. Both facts must remain
disclosed.

## How Selection Bias Is Controlled

- The primary formula and gates remain unchanged until the decision-grade review.
- Results are reported even when negative; failed periods cannot be discarded.
- Any change creates a separately named challenger and resets its prospective clock.
- Challenger results cannot be pooled with primary-candidate results.
- One-position-at-a-time execution is used in every comparison.
- Trading-day bootstrap replaces independent-trade confidence intervals.
- The review explicitly retains the original search context: 641 strategy groups and
  318 unique instrument/timeframe/variant combinations were inspected.

Selection bias cannot be erased from the old backtest. Freezing does not make the old
selection unbiased; it prevents further adaptation while new independent evidence is
collected.

Retrospective multiple-testing diagnostics such as a deflated Sharpe ratio,
combinatorially symmetric cross-validation/probability of backtest overfitting, and a
stationary-bootstrap reality check should be run across the complete searched candidate
universe. These can quantify how likely the historical winner is to be luck, but they
cannot turn the searched sample into independent validation.

The searched alternatives are not missing. The repository retains the strategy
implementations in `src/orderflow_analyzer/`, the cross-instrument 641-group scorecard
in `reports/canonical_corrected_20260611/strategy_scorecard.md`, and 66,119 MNQ
candidate trade rows across 159 timeframe/variant groups in
`reports/canonical_corrected_20260611/mnq_06_26_trades.csv`. Of the 104 MNQ groups
with at least 20 trades, 26 had positive total R on the searched sample. These are
selection-history records, not independent competitors.

There are two valid future exercises:

1. Validate the already selected primary: run only the frozen primary on untouched
   data. This answers whether its apparent edge survives selection bias.
2. Select a new winner: run the complete eligible candidate universe in a predefined
   development window, select mechanically, then evaluate once on a later untouched
   holdout. The development results cannot also serve as validation.

Fetching or testing every alternative on the same prospective stream before the
primary review would spend that stream as another discovery sample. Depth-dependent
alternatives additionally require depth history; trade-only candidates can be
reconstructed from the lean historical request.

## How Limited History Is Expanded

### Lane A: Genuine Prospective Collection

Continue collecting MNQ and NQ trade, quote, and depth data after June 12, 2026. Every
substantial day counts, including losses, feed problems, holidays, and quiet regimes.

Required decision-grade minimum:

- 200 non-overlapping primary-candidate trades;
- 60 substantial prospective trading days;
- at least two MNQ contract/roll periods;
- both long and short trades;
- separate live and replay provenance reports.

The first 50 trades and 20 days are only an interim failure screen.

### Lane B: Pre-Registered Independent Historical Replication

Before downloading or inspecting outcomes, register one fixed replication request for
older MNQ trade data covering multiple volatility regimes and contracts. The formula
requires aggressor-side trade delta; OHLCV-only history is not a valid replication.

The fixed request is registered at:

```text
reports/pattern_ml_20260612/historical_replication_registration.json
```

The original request included MNQ/NQ `trades` and `mbp-10`. A pre-outcome code and cost
audit found that the frozen formula explicitly disables depth and that MNQ is the actual
replication target. Registration version 2 therefore requests MNQ `trades` only from
January 1, 2023 through March 31, 2026. This reduces the estimated request from roughly
`$6,544` and 11.6 TB to roughly `$771` and 29.6 GB. NQ trades remain an optional,
separately reported portability test estimated at roughly `$404`.

Estimate vendor cost before ordering, but do not change the requested period after
seeing outcome data. No historical replication download has been started.

Use the exact registered formula and costs once on that data. Do not optimize parameters
or select subperiods. Label this lane `historical_replication`, not prospective evidence,
and report it separately.

### Lane C: Execution Confirmation

Paper orders must record:

- signal, submission, acknowledgement, fill, cancel, and exit timestamps;
- intended and actual prices;
- spread and slippage;
- missed/rejected orders;
- IBKR initial and maintenance margin at decision time.

Compare paper fills against the analyzer. A strategy that only works with idealized
signal-close fills fails even if its formula statistics look positive.

## Frozen Gates

At the decision-grade review, require all of:

- payoff ratio at least `1.30`;
- profit factor at least `1.20`;
- positive PnL after removing the best day;
- profit factor at least `1.00` after removing the largest winner;
- positive expectancy after frozen costs;
- trading-day bootstrap 95% lower bounds above zero expectancy and profit factor `1.0`;
- no single direction, session, contract, or month explains all profit;
- acceptable results in both chronological halves;
- actual paper slippage and missed-fill performance remain viable;
- one-contract `$10,000` account stays above the registered margin reserve.

Failing a gate means reject or continue collecting data without changing the primary.

## Operational Commands

After canonical data and the analyzer trade report are refreshed:

```bash
.venv/bin/python scripts/monitor_formula_prospective.py
```

The monitor now:

- reconstructs the analyzer's embedded cost correctly;
- skips overlapping positions;
- reports interim and decision-grade counts;
- computes trading-day bootstrap confidence.

## Research Discipline

Interesting observations may be recorded, but they cannot alter the frozen candidate.
For example, if future longs outperform shorts, that is evidence about the primary's
stability. It is not permission to retroactively declare a long-only primary.

The cleanest evidence is boring: keep collecting, do not tune, and publish the result.
