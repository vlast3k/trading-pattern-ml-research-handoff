# Post-Donchian Next Iteration Plan - 2026-06-21

## Context

Issue #9 selected `mnq_60_donchian_confluence_ge6` as the least weak current strategy-family candidate and advanced it to focused validation.

Issue #11 / PR #12 completed that validation attempt in `available_data_audit` mode because no true post-selection forward cohort exists. The result demoted Donchian from `primary_validation_candidate` to `diagnostic_only`.

Donchian failed for product/research reasons, not infrastructure reasons:

- no true forward cohort exists yet;
- the available-data audit is positive only nominally;
- the result is too concentrated in the largest winner, best day, and best week;
- therefore it cannot be promoted to paper/live or platform implementation.

## Current strategy-family status after Issue #11

| Family | Status | Current decision |
| --- | --- | --- |
| Donchian / range breakout | `diagnostic_only` | Demoted after available-data audit. Do not validate again without true new forward data or a materially different frozen question. |
| EMA pullback | `diagnostic_only` | Local 60m monitor exists but cross-source agreement failed. Keep as diagnostic only. |
| MACD / momentum | `diagnostic_only` | Databento rows were not supported by local canonical evidence. No promotion. |
| Bollinger / volatility expansion | `diagnostic_only` | Some promise but sample/largest-winner issues. No promotion without stricter evidence. |
| RSI reversion | `diagnostic_only` | Local 30m evidence exists but Databento support is sparse. Needs careful re-check, not immediate promotion. |
| ORB / VWAP / prior-day levels | `diagnostic_only` | Useful research facts but no clean validated candidate. |
| Raw SFP / order-flow reversal | `reject` | Keep rejected unless a separate issue brings genuinely new evidence. |

## Strategic interpretation

There is currently **no active primary validation candidate**.

The correct next iteration is not to rush the second-best-looking family into validation. The next step should first update the strategy-family ranking after Donchian's demotion and decide whether any remaining family deserves one focused validation attempt under stricter gates.

The likely outcome may be one of:

1. Promote exactly one remaining family to a tightly scoped validation issue.
2. Keep all families diagnostic and collect true forward data before more validation.
3. Reject the current set as overfit/fragile and broaden discovery.

Any next candidate must be stronger than Donchian on fragility, not merely profitable on a small or selected slice.

## Required next issue

Open a post-Donchian strategy reset issue.

Purpose:

- Update the family ranking after Donchian demotion.
- Use Issue #9, Issue #11, `DATA_INVENTORY.md`, and current reports as source material.
- Decide whether there is still one next validation candidate, or whether all current families should remain diagnostic/rejected.

## Evidence rules for the next ranking

A family cannot be promoted unless the report shows:

- clear candidate ID and frozen definition;
- source lineage and repo-relative data availability;
- at least one local evidence cohort and one longer-history or independent support source, unless the report explicitly justifies why one source is enough;
- enough trades and weeks to avoid single-event promotion;
- positive net after costs;
- PF robustness under slippage;
- max drawdown consistent with one-contract MNQ reality;
- largest-winner share below 50%;
- net excluding largest winner positive;
- no single day/week dominance;
- no retuning to rescue a candidate.

## What not to do next

Do not:

- re-run Donchian validation on the same available-data cohort;
- promote a family only because the post-Donchian field is weak;
- start NinjaTrader order implementation;
- start IBKR/broker integration;
- approve paper/live trading;
- run broad parameter mining without a separate discovery issue;
- hide the fact that no current family may be good enough.

## Recommended worker outputs

Create:

```text
POST_DONCHIAN_STRATEGY_RESET_<DATE>.md
reports/post_donchian_strategy_reset_<DATE>/family_status_after_donchian.csv
reports/post_donchian_strategy_reset_<DATE>/candidate_shortlist.csv
reports/post_donchian_strategy_reset_<DATE>/blocked_candidates.csv
reports/post_donchian_strategy_reset_<DATE>/decision.json
```

The final decision must be exactly one of:

- `advance_one_candidate_to_validation`
- `keep_all_diagnostic_collect_forward_data`
- `reject_current_set_broaden_discovery`

## Product preference entering the next issue

Default skepticism should be high. Donchian was the least weak candidate and failed fragility gates. The next report should be comfortable saying that there is no remaining validation candidate if the evidence does not justify one.

The most plausible families to re-check, in order, are:

1. RSI reversion, because it had some local 30m evidence but weak Databento support.
2. Bollinger / volatility expansion, because it had some Databento rows but sample/largest-winner concerns.
3. ORB / VWAP / prior-day levels, only if exact local confirmation can be found.
4. EMA only as a diagnostic/regime feature, not standalone promotion.

MACD and SFP should not consume near-term validation effort unless new evidence appears.
