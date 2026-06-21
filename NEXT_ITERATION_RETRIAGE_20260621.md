# Next Iteration Retriage - 2026-06-21

Active issue: [#13 Re-rank remaining strategy families after Donchian demotion](https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/13)

## Verdict

**Primary recommendation: `collect_specific_data_first`.**

No remaining strategy family should be advanced to focused validation from the current evidence. Donchian was the prior least-weak candidate and failed the Issue #11 available-data audit because its positive result was dominated by the largest winner, best day, and best week. The remaining families are either diagnostic-only with cross-source disagreement, diagnostic-only with missing local confirmation, or already rejected.

The next action is to first rebuild or import a fresh canonical post-selection OHLCV/order-flow source from raw Ninja exports/replay/live data, then create a repo-relative forward data package for the current diagnostic families before choosing another candidate:

```text
data/local_canonical/post_selection_forward_20260609_plus/
```

Minimum decision target:

- MNQ first, NQ optional.
- Starts after the existing selection/local research window: `2026-06-09`.
- Do **not** source the forward bars from the existing `../trading/data/ninja_canonical_ohlcv_1m/` directory, because `DATA_INVENTORY.md` records that it only runs through `2026-06-08T09:57:00+00:00`.
- Rebuild/import a newer canonical OHLCV/order-flow source from inventory-documented raw Ninja inputs first, then copy or reference the eligible post-`2026-06-08` slice into the package.
- At least 4 calendar weeks, and preferably enough bars/trades for each frozen diagnostic family to reach 30 trades.
- Includes `front_1m.parquet` or equivalent OHLCV context and frozen-trade outputs for the diagnostic families.
- Includes `IMPORT_MANIFEST.json` and source-lineage metadata with file sizes, row counts, timestamp spans, checksums where practical, and inventory-relative provenance.

Until that data exists, the project has **no active primary validation candidate**.

## Inputs Read

- `NEXT_ITERATION_PLAN_20260621.md`
- `STRATEGY_FAMILY_TRIAGE_20260620.md`
- `reports/strategy_family_triage_20260620/family_rankings.csv`
- `DATA_INVENTORY.md`
- `reports/donchian_forward_validation_20260620/VERDICT.md`
- `reports/donchian_forward_validation_20260620/donchian_forward_summary.csv`
- `reports/donchian_forward_validation_20260620/source_lineage.md`
- `EMA_FORWARD_MONITORS_20260620.md`
- `reports/ema_forward_monitor_20260620/VERDICT.md`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.csv`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.json`
- `ISSUE8_EMA_FORWARD_MONITOR_AUDIT_20260620.md`
- `reports/mnq_2025q1_primary_replication/VERDICT.md`
- `reports/pattern_ml_20260612/VERDICT.md`
- `reports/pattern_ml_20260612/DATABENTO_2025Q1_DOWNLOAD_AND_PRIMARY_VERDICT.md`

No broad parameter discovery, Donchian retuning, NinjaTrader execution work, broker work, or paper/live approval was run.

## Updated Family Ranking

| Rank | Family | Updated status | Best known candidate | Reason |
|---:|---|---|---|---|
| 1 | EMA pullback | `diagnostic_only` | `local_raw_60m_ema_pullback` | Best surviving diagnostic monitor: 66 trades, +$2,478 baseline, PF 1.31, DD $1,015, largest-winner share 36.4%, net ex-largest +$1,575. Still not promotable because cross-source EMA evidence failed and this is reused local baseline evidence, not forward validation. |
| 2 | RSI reversion | `diagnostic_only` | MNQ 30m raw RSI reversion | Local strict raw row was relatively clean: 39 trades, +$1,514, PF 1.19, DD $1,149, largest-winner share 29.1%, net ex-largest +$1,074. Not promotable because Databento support was sparse and no frozen forward monitor exists. |
| 3 | Prior-day / ORB / VWAP level variants | `diagnostic_only` | Prior-day rejection / ORB diagnostics | Some Databento practical rows exist, but local confirmation is missing or weak. Needs exact frozen local confirmation before any validation lane. |
| 4 | Bollinger / volatility expansion | `diagnostic_only` | No ready candidate | Some Databento practical/strict rows existed, but no convincing local survivor or stable cross-source candidate is available in handoff evidence. |
| 5 | MACD / momentum | `diagnostic_only` | MNQ 60m `macd_cross` context rows | Databento rows looked strong, but local confirmation failed badly; do not spend next validation budget here. |
| 6 | Donchian / range breakout | `diagnostic_only` | `mnq_60_donchian_confluence_ge6` | Demoted after Issue #11. Positive available-data result failed concentration gates: largest winner 52.4%, best day 83.0%, best week 117.1%. |
| 7 | Raw SFP / order-flow reversal | `reject` | Frozen 1m `vwap_delta_rejection` / SFP-style reversal | Independent 2025Q1 replication rejected the primary thesis: 453 trades, -$679.22, PF 0.89, PF without largest winner 0.86. |

## Why No Focused Validation Candidate Exists

Issue #13 promotion rules require a frozen definition, no one-event dependence, independent or non-selection support, identifiable data, and a validation path without broad search.

None of the remaining families clears all rules:

- EMA has the strongest local diagnostic monitor, but the Databento-style monitor failed locally and the cross-source mismatch is unresolved.
- RSI has a cleaner local row than many families, but the independent Databento support was weak or absent.
- Prior-day/ORB/VWAP and Bollinger have interesting historical rows, but no exact frozen local confirmation strong enough to justify a focused validation attempt.
- MACD has attractive Databento rows but failed local confirmation.
- Donchian just failed the post-selection audit and must not be rescued with the same evidence.
- SFP/order-flow reversal is rejected.

## Exact Next Action

First rebuild/import a fresh canonical post-selection source, then create/import a forward package under:

```text
data/local_canonical/post_selection_forward_20260609_plus/
```

The package should contain:

- `IMPORT_MANIFEST.json`
- `source_lineage.md`
- OHLCV/order-flow context derived from a **fresh rebuilt/imported** canonical source that extends beyond `2026-06-08`; the existing `../trading/data/ninja_canonical_ohlcv_1m/` is selection-window data only and must not be reused as the forward source.
- Source lineage back to inventory-documented raw Ninja inputs, such as raw exports/replay/live data, plus the rebuild/import command or copy/symlink step.
- Frozen diagnostic trade outputs for:
  - `local_raw_60m_ema_pullback`
  - MNQ 30m raw RSI reversion, if its exact definition can be recovered from the prior local evidence
  - prior-day/ORB/VWAP diagnostics only if exact frozen definitions are available
  - Bollinger diagnostics only if exact frozen definitions are available
- Explicit `not_available` rows for any family whose exact frozen definition cannot be reconstructed.

Decision rule for the next issue:

- If one family passes forward gates across this package, open a focused validation issue for that exact frozen candidate.
- If all remain weak or under-sampled, keep all diagnostic and continue forward collection.
- Do not run broad discovery unless a separate issue explicitly chooses that phase.

## Files Created

- `reports/next_iteration_retriage_20260621/VERDICT.md`
- `reports/next_iteration_retriage_20260621/family_status_after_donchian.csv`
- `reports/next_iteration_retriage_20260621/candidate_evidence_matrix.csv`
- `reports/next_iteration_retriage_20260621/data_gap_matrix.csv`
- `reports/next_iteration_retriage_20260621/source_lineage.md`
- `reports/next_iteration_retriage_20260621/triage_metadata.json`

