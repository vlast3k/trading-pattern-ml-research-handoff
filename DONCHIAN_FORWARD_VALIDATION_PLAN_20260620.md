# Donchian Forward Validation Plan - 2026-06-20

## Strategic conclusion from Issue #9

Issue #9 ranked the current strategy families and made one primary recommendation: advance **MNQ 60m Donchian / range breakout with frozen `confluence_score >= 6`** as the next practical validation candidate.

This is **not a trading or paper-trading approval**. The candidate is only the least weak current path because it combines:

- broad Databento support;
- an independently positive local canonical survivor;
- simple OHLCV-based implementation logic;
- better validation promise than EMA, MACD, Bollinger, ORB/VWAP, or SFP/order-flow reversal.

The core risk is still material: the local survivor has only 47 trades and high largest-winner dependence. The next work must therefore validate the frozen candidate on data that was not used to select it.

## Candidate under validation

- Candidate ID: `mnq_60_donchian_confluence_ge6`
- Family: `donchian_breakout`
- Instrument: `MNQ`
- Timeframe: `60m`
- Selector: frozen `confluence_score >= 6`
- Trade size for reporting: one MNQ contract
- Status entering this plan: `primary_validation_candidate`
- Status ceiling before forward validation: **not paper-ready, not tradeable**

## What is intentionally not being pursued now

Near-term effort should stop or remain diagnostic for:

- standalone EMA promotion;
- standalone MACD promotion;
- Bollinger / volatility expansion promotion;
- ORB, VWAP reclaim, and prior-day rescue work;
- raw SFP / order-flow reversal rescue;
- NinjaTrader order automation;
- IBKR integration;
- paper/live trading;
- broad parameter search to rescue or improve Donchian.

These can only be reopened through a separate issue with new evidence or a clearly justified research question.

## Data reproducibility requirement

Large/raw/proprietary market data may remain uncommitted and ignored, but it must be placed under a predictable repo-relative path.

Acceptable examples:

```text
data/local_canonical/...
data/databento/...
data/manual_imports/...
```

Validation scripts and reports must not depend on undocumented absolute local paths such as `C:\Users\...`.

If external local data is needed, the worker must document one of:

- a repo-relative copy path;
- a repo-relative symlink path;
- an import step that places the data under `data/...` or another documented ignored repo-relative directory.

The first validation issue must produce a source-lineage artifact before the trading result can be accepted.

## Phase 1: frozen forward/local validation

Goal: test whether `mnq_60_donchian_confluence_ge6` survives on newly appended local canonical data not used to select the candidate.

Required outputs:

```text
reports/donchian_forward_validation_<DATE>/VERDICT.md
reports/donchian_forward_validation_<DATE>/donchian_forward_summary.csv
reports/donchian_forward_validation_<DATE>/donchian_forward_config.json
reports/donchian_forward_validation_<DATE>/source_lineage.md
reports/donchian_forward_validation_<DATE>/input_manifest.json
reports/donchian_forward_validation_<DATE>/join_checks.csv
reports/donchian_forward_validation_<DATE>/selected_trades.csv.gz
```

Minimum evidence target:

- at least 4 calendar weeks; and
- at least 30 forward/local trades.

If fewer than 30 trades are available after 6 weeks, report `under_sampled` instead of pass/fail.

Pass gates:

- net profit after stated commissions/fees is positive;
- PF >= 1.10 at baseline cost;
- PF >= 1.05 under 2 ticks per side slippage;
- max drawdown <= $2,500 for one MNQ contract;
- largest-winner share < 50%;
- net excluding largest winner remains positive;
- no single day or week explains the majority of the result;
- all input paths, timestamps, session assumptions, and cost assumptions are documented.

Failure / demotion gates:

- net <= 0 after costs;
- PF < 1.0 under 2 ticks per side slippage;
- max drawdown > $2,500 before enough positive expectancy is observed;
- largest-winner share >= 50%;
- net excluding largest winner <= 0;
- data cannot be traced to repo-relative ignored paths;
- formula or selector differs from frozen candidate definition;
- the result requires parameter changes to pass.

Decision after Phase 1:

- If pass: keep the candidate as the only primary validation lane and open a signal-only validation issue.
- If fail: demote Donchian to `diagnostic_only` or `reject`, depending on severity.
- If under-sampled: continue frozen monitoring only; do not promote.

## Phase 2: signal-only implementation validation, only after Phase 1 passes

This phase is explicitly blocked until forward/local validation passes.

Allowed scope:

- signal-only replay or analyzer-vs-platform comparison;
- no live orders;
- no paper orders unless a later issue explicitly approves;
- no IBKR integration;
- no parameter tuning.

Main requirement: platform signals must match analyzer timestamps/levels closely enough to trust implementation fidelity.

## Phase 3: paper-readiness review, only after Phase 2 passes

Paper-readiness is a separate product decision and must include:

- prospective stability;
- cost/slippage sensitivity;
- max drawdown versus account size;
- largest-winner and best-week removal;
- operational feasibility;
- kill-switch and monitoring criteria.

No current issue should jump directly to this phase.

## Next issue to open

Open one issue for Phase 1 only:

**Validate frozen MNQ 60m Donchian `confluence_score >= 6` on newly appended local data.**

The issue should require the source-lineage/data-nesting artifacts first, then the frozen monitor execution.
