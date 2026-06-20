# AGENTS.md

## Repository purpose

This repository is a research handoff for MNQ/NQ strategy analysis across Databento-derived artifacts and local NinjaTrader canonical artifacts.

The goal is reproducible evidence and conservative classification, not immediate automation.

## Core research posture

- Treat every candidate as non-deployable unless an active issue explicitly says otherwise.
- Prefer conservative classifications:
  - `reject`
  - `diagnostic_only`
  - `research_monitor`
  - `primary_validation`
  - `plausibly_tradeable_paper`
- Do not promote a candidate based on one attractive report row.
- Preserve the distinction between historical evidence, local validation, forward monitoring, implementation fidelity, and operational integration.

## Hard scope rules

Unless the active GitHub issue explicitly requests it:

- Do not add platform-specific strategy implementation code.
- Do not work on broker/order-routing integrations.
- Do not tune parameters to improve a result.
- Do not search new variants when the task is an audit, reconciliation, or forward-monitor task.
- Do not download more data unless the issue asks for a specific period and reason.
- Do not close or upgrade a candidate status without writing the evidence and unresolved risks.

## Active task source of truth

For every run:

1. Identify the active GitHub issue number.
2. Read the issue body and latest comments.
3. Treat older issues only as historical context unless the active issue explicitly depends on them.
4. If a `comments-bin/*.md` file is referenced, read it as task instructions.
5. If task instructions conflict with this file, follow the more conservative instruction and report the conflict.

## Required report discipline

Every research or audit report should include:

- files and artifacts read
- exact candidate IDs, variants, filters, and timeframes
- sample size
- net result
- profit factor
- max drawdown
- largest-winner share
- net after largest-winner removal
- cost and slippage assumptions
- split, holdout, or forward period
- unresolved risks
- final classification

## Anti-overfit rules

- Do not silently retune after seeing validation, holdout, or forward results.
- Do not choose a best row without reporting how many rows or families were searched.
- Do not mix discovery data with validation data.
- Forward monitors must use frozen definitions.
- New data may evaluate frozen definitions, not redefine them.

## Join and timestamp checks

When combining artifacts, verify where possible:

- root or symbol consistency
- timeframe consistency
- variant and filter consistency
- entry-time consistency
- session and timezone assumptions
- cost and slippage assumptions

If joins rely only on `trade_id`, report that as a risk unless additional checks are present.

## Output expectations

At the end of each run, report:

- task interpreted
- files changed, if any
- commands or scripts run
- artifacts generated
- tests or checks performed
- acceptance criteria pass/fail
- unresolved risks
- recommended next action

Use explicit `PASS`, `PARTIAL`, `FAIL`, or `RISK` labels for important findings.

## Review guidelines

When reviewing pull requests, focus on obvious P0/P1 implementation blockers that would prevent the local worker or CI from running correctly, or that would materially distort a trading-research conclusion.

Flag serious issues such as:

- Python syntax errors, import errors, broken CLI arguments, or scripts that cannot run.
- Wrong input/output paths that break repeatable worker execution.
- Obvious pandas/dataframe mistakes, missing required columns, empty-frame crashes, timezone mistakes, or invalid metric calculations.
- Accidental parameter tuning, broad discovery, platform implementation, broker integration, or paper/live trading work outside the active issue scope.
- Report logic that hides weak evidence by omitting sample size, drawdown, largest-winner dependence, cost/slippage, or final status.
- Secrets, API keys, account identifiers, or changes that would expose private data.

Do not block pull requests for style, wording, formatting, or artifact-polish issues unless they prevent execution or materially mislead the trading decision.

A useful review result is either `PASS: no obvious P0/P1 implementation blockers found.` or a short `BLOCKERS:` list with file paths, concrete failure modes, and minimal fixes.
