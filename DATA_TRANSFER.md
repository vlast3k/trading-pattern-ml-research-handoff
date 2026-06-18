# Large Data Transfer Notes

This Git repository intentionally does not contain the large market-data payloads.

Copy these manually when the receiving machine needs to rerun or extend the tests:

```text
data/databento_2025q1_replication          ~1.0 GB
data/canonical_databento_mnq_2025q1         ~49 MB
data/canonical_orderflow_1s                ~540 MB, if the receiver lacks it
```

The generated checksum file for the canonical Databento partitions is included at:

```text
data/canonical_databento_mnq_2025q1/SHA256SUMS
CANONICAL_DATABENTO_SHA256SUMS
```

Validate it from the copied canonical data directory:

```bash
cd data/canonical_databento_mnq_2025q1
shasum -a 256 -c /path/to/CANONICAL_DATABENTO_SHA256SUMS
```

Raw Databento checksums already live in the raw package:

```text
data/databento_2025q1_replication/SHA256SUMS
```

Git LFS was not used for this first handoff because the real large files are raw
market data and are better copied directly or uploaded as release assets later.
