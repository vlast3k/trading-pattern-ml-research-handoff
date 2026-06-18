# Selection Bias And IBKR Cost Review

Date checked: June 13, 2026

## Direct Answers

The earlier frozen `$4.98` value did not correspond directly to the current IBKR MNQ
tariff. It was an Apex-era conservative validation hurdle and was removed before any
prospective trades were observed:

| Component | Per side | Round turn |
|---|---:|---:|
| IBKR MNQ commission, first tier | $0.25 | $0.50 |
| CME fee recovery for MNQ | $0.35 | $0.70 |
| Regulatory fee recovery | $0.02 | $0.04 |
| Direct execution fees | $0.62 | $1.24 |
| Modeled one-tick slippage per side | $0.50 | $1.00 |
| Current fee-plus-slippage baseline |  | $2.24 |
| Current modeled validation cost |  | $2.24 |
| Removed Apex-era stress reserve |  | $2.74 |

The IBKR overnight position fee is separate from round-turn execution cost and depends
on excess equity. Observed paper-account statements should ultimately replace all fee
estimates.

Freezing the strategy does not undo its selection bias. `vwap_delta_rejection` was
selected after a broad search, so all April-June 2026 performance remains discovery
evidence. The freeze only prevents additional tuning while independent evidence is
collected.

## The Other Strategies Are Available

The local repository already contains:

- strategy formulas in `src/orderflow_analyzer/`;
- a 641-group cross-instrument scorecard in
  `reports/canonical_corrected_20260611/strategy_scorecard.md`;
- 66,119 MNQ simulated trade rows spanning 159 timeframe/variant groups in
  `reports/canonical_corrected_20260611/mnq_06_26_trades.csv`;
- equivalent NQ trade results in
  `reports/canonical_corrected_20260611/nq_06_26_trades.csv`.

Among the 104 MNQ timeframe/variant groups with at least 20 trades, 26 had positive
total R in the searched sample. The chosen strategy was therefore selected over many
losers and several other apparent winners. That is exactly why its old result must be
treated as selection-biased.

What is missing is older independent order-flow history, not the alternative strategy
definitions. Trade-only candidates can be rerun on the lean Databento trades request.
Depth-confirmed candidates cannot be faithfully reconstructed without depth data.

## Correct Research Design

For the current primary decision, evaluate only the frozen primary on untouched data.
Do not use the prospective stream to shop among all alternatives.

For a new strategy-selection tournament, preregister:

1. the eligible candidate universe;
2. a development period used to rank candidates;
3. one mechanical selection rule;
4. a later untouched holdout used exactly once;
5. multiple-testing diagnostics and publication of every candidate result.

This produces an honest answer to two different questions: whether the current
candidate survives, and whether a new search procedure can repeatedly select useful
strategies.

## Pricing Sources

- IBKR futures commissions:
  https://www.interactivebrokers.com/en/pricing/commissions-futures.php
- IBKR CME exchange and regulatory fee recovery:
  https://www.interactivebrokers.com/en/accounts/fees/CME.php
- IBKR overnight position fees:
  https://www.interactivebrokers.com/en/accounts/fees/overnight-position-fee-europe.php
