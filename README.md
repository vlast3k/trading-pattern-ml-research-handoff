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
- Prospective monitor scripts referenced by `PROSPECTIVE_GATE.md`.
- Python dependency pins for the local research environment.
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

## Python Environment

Install the research Python dependencies before running the scripts:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-pattern-ml.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-pattern-ml.txt
```

The pinned file reflects the local 2026-06-18 environment. It includes
`numpy`, `pandas`, `polars`, `scikit-learn`, `scipy`, `pyarrow`, `joblib`,
`pytest`, `yfinance`, `databento`, and `python-dotenv`. If exact pins do not
have wheels for the receiving Python version, use Python 3.12/3.13 or install
compatible package versions rather than changing research logic.

The prospective monitor dependency chain is:

```text
scripts/monitor_formula_prospective.py
scripts/review_payoff_asymmetry.py
scripts/diagnose_formula_regime_shift.py
scripts/pattern_ml_research.py
```

Sanity tests:

```bash
PYTHONPATH=scripts .venv/bin/python -m unittest \
  scripts/test_pattern_ml_research.py \
  scripts/test_diagnose_formula_regime_shift.py \
  scripts/test_review_payoff_asymmetry.py \
  scripts/test_monitor_formula_prospective.py
```

## Analyzer Variant Flag

The included handoff snapshot under `src/orderflow_analyzer` has the optional
`-variant` flag. For audit/reproduction of the Databento verdict, keep using
this pinned snapshot. If the active Windows analyzer lacks the flag, import only
that small exact-variant filter if selective reruns are needed; an empty
`-variant` should preserve all-variant behavior. Avoid merging unrelated
analyzer changes into the pinned Databento reproduction path.
