# Data Inventory

Generated: 2026-06-21

This file is the starting point for future data searches. It records where the main research datasets live, what each dataset is for, and which folders should be treated as current, historical, raw provenance, or derived reports.

Paths are relative to this handoff repository unless noted. Most large local data is not committed here; it currently lives in the sibling `../trading` workspace or in the Windows NinjaTrader documents folder.

## Known Local Project Folders

Observed under `C:\Users\vlast\develop` on 2026-06-21:

| Folder | Relative path from this repo | Observed role | Observed size |
| --- | --- | --- | ---: |
| Main trading workspace | `../trading/` | Primary local research workspace with raw/canonical data, scripts, NinjaTrader sources, and large reports | 51,849 files, ~20.3 GB |
| GitHub handoff repo | `./` | This repository; compact handoff, issue/PR artifacts, copied subsets, and this inventory | 147 files, ~33 MB before this file |
| Transfer snapshot | `../trading-pattern-ml-transfer/` | Portable snapshot of the earlier trading workspace, mainly canonical v3 order-flow and a small report slice | ~591 MB |
| `trading-pattern-ml-research` | `../trading-pattern-ml-research/` | Not present on this machine when checked | N/A |

## Quick Source Of Truth

| Research need | Start here | Status |
| --- | --- | --- |
| Current Ninja/Rithmic 1-second order-flow, quote, top-book, and depth research | `../trading/data/canonical_orderflow_1s/` | Current local canonical, format v5 |
| Current Ninja-derived OHLCV 1-minute validation | `../trading/data/ninja_canonical_ohlcv_1m/` | Current local OHLCV view |
| Long-history MNQ/NQ price-volume research | `../trading/data/databento_ohlcv_1m/` | Decoded Databento OHLCV view |
| Databento Q1 2025 MNQ trade/delta replication | `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/` | Verified independent trade-only cohort |
| Raw Databento DBN/ZST provenance | `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/` | Raw package |
| Raw NinjaTrader CSV/GZ exports | External: `C:\Users\vlast\Documents\NinjaTrader 8\export\` | Raw local provenance |
| Raw NinjaTrader Market Replay files | External: `C:\Users\vlast\Documents\NinjaTrader 8\db\replay\` | Raw local replay data |
| Handoff-local Donchian Issue #11 subset | `data/local_canonical/donchian_forward_20260620/` | Small copied subset in this repo |
| Portable older canonical snapshot | `../trading-pattern-ml-transfer/data/canonical_orderflow_1s/` | Older v3 snapshot; useful for transfer/history, not current source of truth |

## Canonical Dataset Registry

The sibling trading workspace already has a machine-readable registry:

- `../trading/data/dataset_registry.json`

Use it first when deciding whether two datasets are allowed to be pooled. It declares separate cohorts for Databento, Ninja replay/live, and historical transfer snapshots.

Current registry entries observed:

| Dataset id | Root | Role |
| --- | --- | --- |
| `databento_mnq_2025q1_trades_canonical` | `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/` | Independent trade/delta validation; trade-only, no quotes/depth |
| `databento_mnq_nq_ohlcv_1m_2023_2026q1` | `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/` | Long price-volume history for OHLCV candidates |
| `ninja_orderflow_v5_20260401_20260608` | `../trading/data/canonical_orderflow_1s/` | Current local Ninja/Rithmic order-flow canonical |
| `ninja_orderflow_v3_transfer_snapshot` | `../trading/2026.08.17 - trading transfer/canonical_orderflow_1s/` | Historical snapshot; do not use as current validation source |

## Datasets

### `ninja_orderflow_v5_20260401_20260608`

- Root: `../trading/data/canonical_orderflow_1s/`
- Manifest: `../trading/data/canonical_orderflow_1s/manifest.json`
- Source: NinjaTrader/Rithmic live and replay exports.
- Format: canonical 1-second order-flow v5, 72 columns.
- Observed manifest: version 5, generated `2026-06-14T05:58:05+03:00`.
- Observed partitions: 260.
- Date range: approximately 2026-04-01 through 2026-06-08.
- Instruments: `MNQ 06-26`, `NQ 06-26`, `ES 06-26`, `MES 06-26`, plus small/partial `GC 06-26` and `MGC 06-26` smoke data.
- Features: trades, OHLC from trades, aggressor delta, volume, quotes, top book, and depth.
- Use for: local discovery, order-flow/depth research, and Ninja parity validation.
- Policy: use replay-only subsets for deterministic Playback101 validation. Mixed live/replay/live-only slices are research evidence, not deterministic implementation parity evidence.

Approximate partition sizes observed in `../trading/data/canonical_orderflow_1s/`:

| Instrument group | Files | Approx size |
| --- | ---: | ---: |
| ES | 65 | 232.7 MB |
| MES | 63 | 249.3 MB |
| MNQ | 65 | 296.9 MB |
| NQ | 65 | 236.0 MB |
| GC/MGC | tiny smoke/partial | tiny |

### `ninja_canonical_ohlcv_1m`

- Root: `../trading/data/ninja_canonical_ohlcv_1m/`
- Manifest: `../trading/data/ninja_canonical_ohlcv_1m/manifest.json`
- Built by: `../trading/scripts/build_ninja_canonical_ohlcv_1m.py`
- Files:
  - `../trading/data/ninja_canonical_ohlcv_1m/front_1m.parquet`
  - `../trading/data/ninja_canonical_ohlcv_1m/manifest.json`
- Observed roots: `MNQ`, `NQ`.
- Observed rows: 124,112.
- Observed UTC range: `2026-04-01T11:00:00+00:00` through `2026-06-08T09:57:00+00:00`.
- Use for: local OHLCV validation and comparison against Databento OHLCV strategy research.

### `databento_mnq_nq_ohlcv_1m_2023_2026q1`

- Decoded view root: `../trading/data/databento_ohlcv_1m/`
- Raw package root: `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/`
- Raw package checksum manifest: `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/SHA256SUMS`
- Built by: `../trading/scripts/build_databento_ohlcv_1m_views.py`
- Files in decoded view:
  - `../trading/data/databento_ohlcv_1m/front_1m.parquet`
  - `../trading/data/databento_ohlcv_1m/outrights_1m.parquet`
  - `../trading/data/databento_ohlcv_1m/front_rolls_daily.csv`
  - `../trading/data/databento_ohlcv_1m/manifest.json`
- Source: Databento GLBX.MDP3 OHLCV-1m and definitions.
- Observed decoded UTC range: `2023-01-02T23:00:00+00:00` through `2026-03-31T23:59:00+00:00`.
- Observed roots: `MNQ`, `NQ`.
- Observed roll rule: daily dominant outright by total UTC-day volume per root.
- Observed counts:
  - Outright rows: 3,342,965.
  - Front rows: 2,295,226.
  - Roll days: 2,024.
- Use for: long-history price/volume strategy families such as MACD, RSI, Donchian, Bollinger, VWAP-without-delta, and portability checks.
- Important limitation: no aggressor delta, quotes, top-book, or depth.

Raw package observed in `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/`:

| File group | Count | Approx size |
| --- | ---: | ---: |
| `.zst` Databento DBN files | 81 | 1,028.2 MB |
| `.json` metadata/manifests | 10 | 0.3 MB |

Important subfolders:

- `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/mnq_trades_2025q1/`
- `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/mnq_nq_ohlcv_1m_2023_2026q1/`
- `../trading/2026.08.17 - trading transfer/databento_2025q1_replication/mnq_nq_definitions_2023_2026q1/`

### `databento_mnq_2025q1_trades_canonical`

- Root: `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/`
- Manifest: `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/manifest.json`
- Checksum manifest: `../trading/2026.08.17 - trading transfer/CANONICAL_DATABENTO_SHA256SUMS`
- Source: Databento GLBX.MDP3 trades.
- Format: canonical 1-second trade-only order-flow, 32 columns.
- Observed partitions: 77 date partitions.
- Observed size: approximately 48.5 MB.
- Date range: 2025-01-01 through 2025-03-31.
- Instruments: `MNQH5`, `MNQM5`.
- Features: trades, trade OHLC, aggressor delta, volume.
- Missing features: quotes, top-book, depth.
- Use for: independent trade/delta validation.
- Policy: do not mix with Ninja/Rithmic quote/depth data as if it were the same cohort.

Note: this handoff repo also has `data/canonical_databento_mnq_2025q1/SHA256SUMS`, but the actual canonical partitions are currently referenced in the sibling `../trading/...` transfer folder.

### `ninja_orderflow_v3_transfer_snapshot`

- Root: `../trading/2026.08.17 - trading transfer/canonical_orderflow_1s/`
- Manifest: `../trading/2026.08.17 - trading transfer/canonical_orderflow_1s/manifest.json`
- Source: transferred Ninja canonical data from another machine.
- Format: canonical order-flow v3 profile-limited transfer.
- Observed size: approximately 540 MB.
- Status: historical snapshot, not current.
- Policy: do not use for current validation unless an issue explicitly asks for historical comparison. Format v3 was superseded by local v5 after partition/time contamination problems were found and corrected.

### `trading-pattern-ml-transfer` Portable Snapshot

- Root: `../trading-pattern-ml-transfer/`
- Canonical data root: `../trading-pattern-ml-transfer/data/canonical_orderflow_1s/`
- Manifest: `../trading-pattern-ml-transfer/data/canonical_orderflow_1s/manifest.json`
- Transfer manifest: `../trading-pattern-ml-transfer/TRANSFER_MANIFEST.csv`
- Report slice: `../trading-pattern-ml-transfer/reports/canonical_corrected_20260611/`
- Observed canonical files: 131 files, approximately 539.4 MB.
- Observed report slice: 16 files, approximately 51.7 MB.
- Manifest version: 3, generated `2026-06-11T10:19:50+03:00`.
- Observed instruments in manifest: ES, MES, MNQ, NQ, plus tiny GC/MGC smoke/partial data.
- Date range: approximately 2026-04-01 through 2026-06-08.
- Status: portable historical snapshot.
- Policy: do not treat this as the current canonical source. Prefer `../trading/data/canonical_orderflow_1s/` v5 for current Ninja/Rithmic research.

### Raw NinjaTrader Exports

- External root: `C:\Users\vlast\Documents\NinjaTrader 8\export\`
- Observed CSV files: 1,279, approximately 46.6 GB.
- Observed `.gz` files: 15,324, approximately 33.4 GB.
- Includes:
  - `candidate_signals_OrderFlowNqVwapDeltaRejectionStrategy_MNQ_06-26.csv`
  - `candidate_validation_archive/postfix_full_20260614/`
  - `orderflow_MNQ_06-26_20260612_...`
  - `replayfill_orderflow_*`
- Use for: raw provenance, rebuilding canonical Ninja datasets, and investigating exporter/replay issues.
- Portability note: this folder is outside both repos. To make a run portable, copy selected raw exports under a documented repo-relative ignored path, or document a symlink/import step.

### Raw NinjaTrader Market Replay

- External root: `C:\Users\vlast\Documents\NinjaTrader 8\db\replay\`
- Observed `.nrd` files: 220, approximately 28.9 GB.
- Observed instrument folders:
  - `ES 06-26`
  - `MES 06-26`
  - `MNQ 06-26`
  - `NQ 06-26`
- Use for: Playback101 deterministic Ninja validation and replay-driven exports.
- Portability note: this folder is large and external. Future reports should document the import/copy/symlink step if they require these files.

### Handoff-Local Donchian Issue #11 Subset

- Root: `data/local_canonical/donchian_forward_20260620/`
- Import manifest: `data/local_canonical/donchian_forward_20260620/IMPORT_MANIFEST.json`
- README: `data/local_canonical/donchian_forward_20260620/README.md`
- Purpose: small copied subset used by Issue #11 / PR #12 Donchian forward validation work.
- Important files:
  - `data/local_canonical/donchian_forward_20260620/ohlcv_context/front_1m.parquet`
  - `data/local_canonical/donchian_forward_20260620/ohlcv_context/manifest.json`
  - `data/local_canonical/donchian_forward_20260620/frozen_registry_reference/trades_with_context.csv.gz`
  - `data/local_canonical/donchian_forward_20260620/frozen_registry_reference/summary.csv`
  - `data/local_canonical/donchian_forward_20260620/candidate_trades/trades_nonoverlap.csv.gz`
  - `data/local_canonical/donchian_forward_20260620/candidate_trades/summary_nonoverlap.csv`
- Known caveat from prior work: this subset was enough to expose Issue #11 data-lineage incompleteness, but it should not be treated as a complete forward validation dataset unless the missing true forward trades input is supplied or the issue scope changes.

## Derived Reports And Research Outputs

Primary report folders in sibling `../trading/reports/`:

| Folder | Approx size | Notes |
| --- | ---: | --- |
| `../trading/reports/canonical_corrected_v5_20260614/` | 447.1 MB | Corrected v5 MNQ analysis used after v3/v4 invalidations |
| `../trading/reports/databento_ohlcv_eval_20260618/` | 71.0 MB | Databento OHLCV evaluations |
| `../trading/reports/databento_ohlcv_eval_20260618_large_tf/` | 11.8 MB | Larger timeframe OHLCV evaluation |
| `../trading/reports/databento_ohlcv_eval_20260618_macd_zero/` | 0.9 MB | MACD zero-line related evaluation |
| `../trading/reports/databento_ohlcv_eval_20260619_expanded/` | 26.9 MB | Expanded Databento OHLCV families |
| `../trading/reports/databento_ohlcv_eval_20260619_new_families_smoke/` | 2.6 MB | Smoke results for newer families |
| `../trading/reports/ninja_canonical_ohlcv_eval_20260619/` | 0.2 MB | Ninja OHLCV evaluation |
| `../trading/reports/ninja_canonical_ohlcv_eval_20260619_expanded/` | 1.6 MB | Expanded Ninja OHLCV evaluation |
| `../trading/reports/frozen_ohlcv_selectors_ninja_20260619/` | 37.3 MB | Frozen selector validation evidence |
| `../trading/reports/frozen_ohlcv_selectors_ninja_20260619_expanded/` | 37.6 MB | Expanded frozen selector evidence |
| `../trading/reports/frozen_candidate_registry_validation_20260619/` | 37.4 MB | Frozen candidate registry validation |
| `../trading/reports/ema_pullback_reconciliation_20260619/` | 37.6 MB | EMA pullback reconciliation |
| `../trading/reports/ema_forward_monitor_20260620/` | 0.1 MB | EMA forward monitor |

Historical or superseded large analysis folders in sibling `../trading/reports/`:

| Folder | Approx size | Status |
| --- | ---: | --- |
| `../trading/reports/canonical_all_20260610/` | 1,786.8 MB | Historical pre-correction output |
| `../trading/reports/canonical_corrected_20260611/` | 1,733.1 MB | Historical corrected generation |
| `../trading/reports/canonical_corrected_v4_20260613/` | 431.4 MB | Superseded by v5 |
| `../trading/reports/continuous_all_20260608/` | 491.2 MB | Historical continuous-data output |
| `../trading/reports/runtime/` | 5.3 GB | Logs/runtime output, not a curated dataset |

Handoff-local report folders:

- `reports/pattern_ml_20260612/`
- `reports/mnq_2025q1_primary_replication/`
- `reports/ema_forward_monitor_20260620/`
- `reports/strategy_family_triage_20260620/`
- `reports/donchian_forward_validation_20260620/`

## Secondary BTC Research Path

- Root: `../trading/data/coinbase/`
- Main subfolders:
  - `../trading/data/coinbase/btc_usd/raw/`
  - `../trading/data/coinbase/btc_usd/bars/`
  - `../trading/data/coinbase/depth_smoke/`
  - `../trading/data/coinbase/depth_batch_test/`
- Use for: research-only BTC public-data stop-sweep/SFP thesis validation.
- Policy: do not request Coinbase account credentials and do not place live orders for this research path.

## Important Documentation

Sibling `../trading` docs:

- `../trading/DATABENTO_NINJA_RESEARCH_MERGE_REPORT_20260618.md`
- `../trading/CANONICAL_ORDERFLOW.md`
- `../trading/PATTERN_ML_RESEARCH_HANDOFF_2026-06-12.md`
- `../trading/OHLCV_META_SELECTOR_RESEARCH_20260619.md`
- `../trading/ORDERFLOW_ANALYZER.md`
- `../trading/BTC_TO_MNQ_TRANSFER_RESEARCH.md`
- `../trading/SESSION_HANDOVER_2026-06-09.md`
- `../trading/REPLAY_AUTOMATION.md`

Transferred handoff docs:

- `../trading/2026.08.17 - trading transfer/session_handoff_20260614/README.md`
- `../trading/2026.08.17 - trading transfer/session_handoff_20260614/DATABENTO_NINJA_MERGE_GUIDE.md`

This handoff repo docs:

- `README.md`
- `AGENTS.md`
- `ANSWER_TO_OTHER_CODEX_2026-06-18.md`
- `DONCHIAN_FORWARD_VALIDATION_PLAN_20260620.md`
- `docs/CANONICAL_ORDERFLOW.md`
- `docs/ORDERFLOW_ANALYZER.md`
- `docs/PATTERN_ML_RESEARCH_HANDOFF_2026-06-12.md`
- `docs/MNQ_VALIDATION_PROTOCOL_2026-06-13.md`

## Candidate Registry

Candidate definitions and policy live in:

- `../trading/data/candidate_registry.json`

Observed candidate IDs:

- `vwap_delta_rejection_1m`
- `raw_sfp`
- `delta_sfp`
- `macd_cross`
- `donchian_volume_delta`
- `rsi_reversion`
- `prior_rth_vwap_reclaim`
- `depth_delta_momentum`

Use this registry before interpreting reports as strategy candidates. Some candidates are explicitly rejected or diagnostic-only and should not be promoted from a single attractive row.

## Search Protocol For Future Sessions

When asked to find data, start with this order:

1. Read this file.
2. Read `../trading/data/dataset_registry.json`.
3. Read the relevant manifest under the dataset root, especially:
   - `../trading/data/canonical_orderflow_1s/manifest.json`
   - `../trading/data/ninja_canonical_ohlcv_1m/manifest.json`
   - `../trading/data/databento_ohlcv_1m/manifest.json`
   - `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/manifest.json`
4. Only then inspect raw/external folders:
   - `C:\Users\vlast\Documents\NinjaTrader 8\export\`
   - `C:\Users\vlast\Documents\NinjaTrader 8\db\replay\`
5. Keep cohorts separate unless a report explicitly documents compatible schema, timestamp, instrument, session, and provenance assumptions.

Useful local commands from this repo root:

```powershell
Get-Content ..\trading\data\dataset_registry.json -Raw
Get-Content ..\trading\data\canonical_orderflow_1s\manifest.json -Raw
Get-Content ..\trading\data\ninja_canonical_ohlcv_1m\manifest.json -Raw
Get-Content ..\trading\data\databento_ohlcv_1m\manifest.json -Raw
Get-ChildItem '..\trading\reports' -Directory
Get-ChildItem 'C:\Users\vlast\Documents\NinjaTrader 8\export' -File
```

## Portability Guidance

This handoff repo does not contain all large source data. For another machine, either:

1. Copy selected required data into a documented ignored repo-relative folder such as `data/local_canonical/<task-id>/`, with an `IMPORT_MANIFEST.json`, or
2. Recreate the sibling `../trading` layout, or
3. Document symlinks from this repo to the local data roots.

Validation scripts and reports should not require unmentioned absolute paths. If an absolute path such as `C:\Users\vlast\Documents\NinjaTrader 8\export\` is required, the report must explain the copy, import, or symlink step.
