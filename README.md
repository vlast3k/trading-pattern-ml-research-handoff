# Trading Pattern ML Research Handoff

Private handoff repository for the Databento/NinjaTrader MNQ research merge.

Start here:

1. `ANSWER_TO_OTHER_CODEX_2026-06-18.md`
2. `docs/PATTERN_ML_RESEARCH_HANDOFF_2026-06-12.md`
3. `docs/MNQ_VALIDATION_PROTOCOL_2026-06-13.md`
4. `reports/mnq_2025q1_primary_replication/VERDICT.md`
5. `reports/pattern_ml_20260612/DATABENTO_2025Q1_DOWNLOAD_AND_PRIMARY_VERDICT.md`

## What Is Included

- Databento Q1 2025 primary replication reports.
- Pattern/ML research reports and research-only feature outputs.
- Current local `src/orderflow_analyzer` source snapshot.
- Scripts needed to reproduce the Databento conversion and primary summary.
- Source/report checksum manifests.
- Checksums for the separate canonical Databento data transfer.

## What Is Not Included

- `.env`, API keys, broker credentials, or Codex auth files.
- Raw Databento DBN/Zstd package.
- Canonical Databento CSV partitions.
- Raw NinjaTrader exports.
- Raw Codex JSONL session logs.

See `DATA_TRANSFER.md` for the large files that should be copied manually.

## Reproducibility Caveat

This workspace was not a Git checkout when packaged, so no commit hash exists.
Use `SOURCE_SHA256SUMS` and `REPORTS_SHA256SUMS` as the reproducibility anchor for
the included source and reports.

The frozen Databento primary verdict rejected the MNQ 1-minute
`vwap_delta_rejection` candidate. Do not reinterpret that as proof that every
strategy fails, and do not retune the rejected primary on the same Q1 data.
