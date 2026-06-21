# Donchian Forward Validation Local Data Package

This repo-relative package supports GitHub issue #11:

`data/local_canonical/donchian_forward_20260620/`

The payload files are intentionally ignored by git because they are local market-data artifacts. Copy this whole directory to the same repo-relative path on another machine before running the issue #11 validation.

## Contents

- `candidate_trades/`: local Ninja canonical OHLCV candidate trades and summaries copied from the original trading workspace.
- `frozen_registry_reference/`: prior frozen-registry reference outputs used for schema and prior-evidence lineage, not as new forward evidence.
- `ohlcv_context/`: local canonical 1-minute OHLCV front-contract context.
- `IMPORT_MANIFEST.json`: repo-relative file list with sizes, row counts, timestamp spans, columns, and SHA-256 checksums.

## Forward Validation Input

Issue #11 requires a forward/local trades-with-context file that was not used to choose the candidate. Place that file at:

`data/local_canonical/donchian_forward_20260620/forward_trades/trades_with_context.csv.gz`

Until that file exists, `scripts/run_donchian_forward_validation.py` should report `incomplete_data_lineage` and must not interpret the copied reference cohort as a forward validation result.

## Source Workspace

The files were copied from the local Windows trading workspace:

- `reports/frozen_candidate_registry_validation_20260619/`
- `reports/ninja_canonical_ohlcv_eval_20260619_expanded/`
- `data/ninja_canonical_ohlcv_1m/`

Do not hard-code those original absolute paths in validation scripts. Use the repo-relative paths under this package.
