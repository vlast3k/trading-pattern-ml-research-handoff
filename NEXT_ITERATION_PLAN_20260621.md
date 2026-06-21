# Next Iteration Plan After Donchian Demotion - 2026-06-21

## Current product state

Issue #11 / PR #12 closed the Donchian validation lane.

`mnq_60_donchian_confluence_ge6` was tested in `available_data_audit` mode because no true post-selection forward trades-with-context file exists. The available local/reference cohort remained nominally positive, but failed robustness gates:

- largest winner explained at least 50% of net profit;
- best day explained at least 50% of net profit;
- best week explained at least 50% of net profit.

Decision: Donchian is demoted from `primary_validation_candidate` to `diagnostic_only`.

There is now no active primary validation candidate.

## Strategic interpretation

The Donchian result is useful because it prevented premature implementation. Issue #9 had selected Donchian as the least-weak validation candidate, but Issue #11 showed the candidate is too dependent on a small number of favorable events.

The next step is not to rescue Donchian. The next step is to re-rank the remaining strategy families with Donchian removed from the primary lane.

## Updated family statuses

| Family | Status after Issue #11 | Notes |
| --- | --- | --- |
| Donchian / range breakout | `diagnostic_only` | Failed available-data robustness gates; do not rescue without new evidence. |
| EMA pullback | `diagnostic_only` | Local raw 60m positive but cross-source mismatch; Databento-style 15m failed locally. |
| MACD / momentum | `diagnostic_only` | Local confirmation previously failed; do not promote from Databento-only strength. |
| Bollinger / volatility expansion | `diagnostic_only` | Some promising rows, but prior local sample/large-winner concerns. |
| ORB / VWAP / prior-day levels | `diagnostic_only` | Useful research facts, no clear promotion candidate. |
| RSI reversion | `diagnostic_only` | Local 30m raw signal looked relatively clean, but Databento support was sparse. |
| Raw SFP / order-flow reversal | `reject` | Primary replication rejected; do not reopen except as negative reference. |

## Next iteration objective

Issue #13 should determine exactly one next action:

1. advance one non-Donchian family to a focused validation attempt;
2. collect a specific new data slice before choosing a candidate;
3. broaden discovery under tighter gates;
4. stop current families and wait for more forward data.

The default expectation is that no candidate should be promoted unless the report finds materially stronger evidence than Donchian had.

## Evidence gates for the next candidate

A new focused validation candidate must have:

- frozen definition;
- enough trades/calendar coverage to avoid one-event dependence;
- positive net after stated cost assumptions;
- drawdown compatible with one MNQ contract risk;
- positive net excluding largest winner;
- largest-winner share below 50%;
- best-day and best-week concentration below 50%;
- at least one independent or non-selection cohort supporting the idea;
- data source clearly identified in `DATA_INVENTORY.md` or a repo-relative package.

If no family satisfies this, the correct answer is to say no primary candidate exists.

## Data posture

`DATA_INVENTORY.md` is now the source map. Workers should use it before deciding that data does or does not exist.

Important sources:

- current Ninja/Rithmic order-flow v5: `../trading/data/canonical_orderflow_1s/`;
- current Ninja OHLCV 1m: `../trading/data/ninja_canonical_ohlcv_1m/`;
- long-history Databento OHLCV: `../trading/data/databento_ohlcv_1m/`;
- verified Databento 2025 Q1 trade/delta cohort: `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/`;
- handoff-local Donchian Issue #11 subset: `data/local_canonical/donchian_forward_20260620/`.

Large/raw data may remain uncommitted, but reports must explain source lineage through inventory-relative or repo-relative paths.

## Recommended worker task

Open or use Issue #13: `Re-rank remaining strategy families after Donchian demotion`.

Required outputs:

```text
NEXT_ITERATION_RETRIAGE_<DATE>.md
reports/next_iteration_retriage_<DATE>/VERDICT.md
reports/next_iteration_retriage_<DATE>/family_status_after_donchian.csv
reports/next_iteration_retriage_<DATE>/candidate_evidence_matrix.csv
reports/next_iteration_retriage_<DATE>/data_gap_matrix.csv
```

The final answer must be a product decision, not just a score table.

## Prohibited next actions

Do not:

- retune Donchian;
- promote Donchian again using the same evidence;
- paper/live trade any current candidate;
- add broker or order execution code;
- choose a new candidate only because one row is profitable;
- ignore largest-winner, best-day, or best-week concentration;
- treat selection-period evidence as forward validation.

## Desired outcome of Issue #13

The ideal output is one of:

- `advance_family_to_focused_validation`: with exact frozen candidate and data source;
- `collect_specific_data_first`: with exact missing data and why it matters;
- `broaden_discovery_with_tighter_gates`: with bounded families/features, not open-ended tuning;
- `no_current_candidate_wait_for_forward_data`: if all current families are too weak.

Only one recommendation should be made.
