# Donchian Forward Validation Source Lineage

Verdict gate: `incomplete_data_lineage`

This artifact documents repo-relative inputs for GitHub issue #11. Large payload files may be ignored by git, but they must exist at the listed repo-relative paths before a trading result can be accepted.

## Gate Reasons

- No eligible forward trades-with-context input exists under the repo-relative data package.

## Inputs

| Role | Path | Exists | Ignored | Rows | First Timestamp | Last Timestamp | SHA-256 |
|---|---|---:|---:|---:|---|---|---|
| data_root | `data/local_canonical/donchian_forward_20260620` | True | False |  |  |  | `` |
| package_import_manifest | `data/local_canonical/donchian_forward_20260620/IMPORT_MANIFEST.json` | True | False |  |  |  | `cfc5ebbc82eed029604fecd93458cfbef219cf96d046f4046f46443dc1dabf7a` |
| required_forward_trades | `data/local_canonical/donchian_forward_20260620/forward_trades/trades_with_context.csv.gz` | False | None |  |  |  | `` |
| reference_trades_not_forward | `data/local_canonical/donchian_forward_20260620/frozen_registry_reference/trades_with_context.csv.gz` | True | True | 1164 | 2026-04-01T21:30:00+00:00 | 2026-06-08T00:30:00+00:00 | `aa4f635c9610cc45c98b223d128c536f58c6b9e77a97425fd888fe259dc249a9` |
| candidate_trades_context_source | `data/local_canonical/donchian_forward_20260620/candidate_trades/trades_nonoverlap.csv.gz` | True | True | 7696 | 2026-04-01T14:45:00+00:00 | 2026-06-08T02:30:00+00:00 | `a6f034342c6e54c95d37932fd15e99e7a02fe06778ac5b42eb929b0a5e412454` |
| ohlcv_context | `data/local_canonical/donchian_forward_20260620/ohlcv_context/front_1m.parquet` | True | True |  |  |  | `7e3ca0f701f16cda9e7e75d165b715886e21370c0b83b8974d1fd803737f9763` |

## Transfer Rule

To reproduce on another machine, copy the ignored payload files under the same repo-relative `data/local_canonical/donchian_forward_20260620/` directory and keep `IMPORT_MANIFEST.json` in sync.
