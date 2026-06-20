# Issue #7 audit command

Current active issue: GitHub Issue #7 only.

Treat earlier issues as historical context about previous research outcomes and known non-survivors. Do not treat earlier issues as active implementation tickets unless Issue #7 explicitly requires them as context.

## Task

Audit the completed EMA pullback reconciliation report. This is an audit and closure-readiness check, not a continuation of discovery or optimization.

## Required inputs

Read:

- GitHub Issue #7 body and latest comments
- `EMA_PULLBACK_RECONCILIATION_20260619.md`
- `reports/ema_pullback_reconciliation_20260619/VERDICT.md`
- `reports/ema_pullback_reconciliation_20260619/ema_filter_summary.csv`
- `reports/ema_pullback_reconciliation_20260619/ema_month_summary.csv`
- broader discovery report only as background context

## Scope constraints

Do not:

- tune EMA parameters
- search for improved EMA variants
- implement platform-specific strategy code
- perform brokerage or execution-integration work
- download additional data
- promote EMA beyond the evidence already in the reports

## Audit questions

Assess:

1. Does Issue #7 satisfy all stated acceptance criteria?
2. Is the `diagnostic_only` verdict justified by the reported evidence?
3. Are the frozen forward monitors precisely defined enough to be rerun without retuning?
4. Are there any leakage, timestamp, session, split, cost/slippage, largest-winner, or report-wording problems?
5. Should Issue #7 be closed, kept open, or followed by a new forward-monitor issue?

## Required output

Return:

- pass/fail per acceptance criterion
- concrete file references where possible
- unresolved risks
- recommendation: close #7, keep #7 open, or create a specific next issue

## Expected posture

Be conservative. The audit should prefer `diagnostic_only` unless the report evidence clearly supports a stronger classification. No candidate should be promoted by this audit alone.

## Original full-intent notes

The orchestrator should understand this as an instruction to audit, not to act on markets or automate execution. It should explicitly avoid:

- NinjaTrader strategy implementation
- IBKR integration or order-related work
- paper/live trading decisions
- strategy rescue work through further parameter search

The intended result is an evidence-quality assessment and a recommendation about issue state only.