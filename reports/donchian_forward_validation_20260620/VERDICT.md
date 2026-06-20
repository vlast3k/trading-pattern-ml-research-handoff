# Donchian Forward Validation Verdict

Verdict: `incomplete_data_lineage`

Candidate: `mnq_60_donchian_confluence_ge6`

This report does not approve paper/live trading. It is only the issue #11 frozen forward/local validation monitor.

## Reasons

- No eligible forward trades-with-context input exists under the repo-relative data package.

## Join And Lineage Checks

| Check | Status | Detail |
|---|---|---|
| data_root_repo_relative | pass | data/local_canonical/donchian_forward_20260620 |
| package_import_manifest_repo_relative | pass | data/local_canonical/donchian_forward_20260620/IMPORT_MANIFEST.json |
| reference_trades_not_forward_repo_relative | pass | data/local_canonical/donchian_forward_20260620/frozen_registry_reference/trades_with_context.csv.gz |
| candidate_trades_context_source_repo_relative | pass | data/local_canonical/donchian_forward_20260620/candidate_trades/trades_nonoverlap.csv.gz |
| ohlcv_context_repo_relative | pass | data/local_canonical/donchian_forward_20260620/ohlcv_context/front_1m.parquet |
| required_forward_trades_exists | fail | data/local_canonical/donchian_forward_20260620/forward_trades/trades_with_context.csv.gz |

## Summary

| Scope | Slippage | Trades | Weeks | Net | PF | Max DD | Largest Share | Net Ex Largest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full:all | 0.0 | 0 | 0 | $0 | 0.00 | $0 |  | $0 |
| full:all | 1.0 | 0 | 0 | $0 | 0.00 | $0 |  | $0 |
| full:all | 2.0 | 0 | 0 | $0 | 0.00 | $0 |  | $0 |
