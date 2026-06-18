# Answer To Other Codex Session

Date: 2026-06-18

This response was checked against the local filesystem and the raw Codex session
log. Items marked unavailable were not found locally.

## Package Contents

This transfer package includes:

- `reports/mnq_2025q1_primary_replication/`
- `reports/pattern_ml_20260612/`
- `src/orderflow_analyzer/`
- relevant Databento / ML scripts under `scripts/`
- generated canonical Databento checksums under
  `data/canonical_databento_mnq_2025q1/SHA256SUMS`
- `SOURCE_SHA256SUMS` and `REPORTS_SHA256SUMS`

It does not include raw Databento DBN/Zstd files or the 49 MB canonical Databento
CSV partitions. Those remain separate large data transfers.

## 1. Databento DBN/Zstd To Canonical Converter

Available locally:

```text
scripts/convert_databento_trades_to_canonical.py
```

The script is included in this package.

Final command sequence reconstructed from the session log:

```bash
rm -rf data/canonical_databento_mnq_2025q1 reports/mnq_2025q1_primary_replication
.venv/bin/python scripts/convert_databento_trades_to_canonical.py
```

Important semantic correction: an initial unpublished conversion had Databento
side `A` and `B` reversed. That output was discarded. The final converter and
canonical manifest use:

```text
A -> sell_volume
B -> buy_volume
N -> unknown_volume
```

The final canonical manifest is:

```text
data/canonical_databento_mnq_2025q1/manifest.json
```

It records 77 daily partitions, dominant MNQ contract by UTC day, and the side
mapping source.

## 2. Full Databento Primary Replication Reports

Available and included:

```text
reports/mnq_2025q1_primary_replication/
reports/pattern_ml_20260612/
```

Most relevant files:

```text
reports/mnq_2025q1_primary_replication/primary_nonoverlapping_trades.csv
reports/mnq_2025q1_primary_replication/mnq_databento_trades.csv
reports/mnq_2025q1_primary_replication/summary.json
reports/mnq_2025q1_primary_replication/VERDICT.md
reports/pattern_ml_20260612/prospective_monitor/candidate_registry.json
reports/pattern_ml_20260612/historical_replication_registration.json
reports/pattern_ml_20260612/budget_constrained_replication_plan.json
```

`primary_nonoverlapping_trades.csv` is the 453-trade one-position-at-a-time
primary series. `mnq_databento_trades.csv` contains the 461 raw simulated
formula trades before the stricter non-overlap summary.

Bootstrap output exists in:

```text
reports/mnq_2025q1_primary_replication/summary.json
```

There is no separate standalone bootstrap CSV found locally.

No dedicated shell command log file was found. The raw Codex JSONL contains the
tool calls, and the key commands are reconstructed here.

Primary analyzer command:

```bash
mkdir -p reports/mnq_2025q1_primary_replication
go run ./src/orderflow_analyzer \
  -canonical-dir data/canonical_databento_mnq_2025q1 \
  -instrument mnq \
  -tf 1 \
  -variant vwap_delta_rejection \
  -commission-round-turn 2.24 \
  -slippage-ticks 0 \
  -point-value 2 \
  -tick-size 0.25 \
  -out reports/mnq_2025q1_primary_replication
```

The summary/verdict were produced by:

```bash
.venv/bin/python scripts/summarize_primary_replication.py
```

That script is included.

## 3. Analyzer Source Version

No git commit hash is available from this machine. This workspace is not a Git
checkout:

```text
fatal: not a git repository (or any of the parent directories): .git
```

Best available reproducibility artifact is the included local source snapshot:

```text
src/orderflow_analyzer/
go.mod
SOURCE_SHA256SUMS
```

Critical local file mtimes around the primary run:

```text
2026-06-13T17:48:13+0300 src/orderflow_analyzer/main.go
2026-06-13T17:48:13+0300 src/orderflow_analyzer/types.go
2026-06-13T17:49:16+0300 scripts/convert_databento_trades_to_canonical.py
2026-06-13T18:23:27+0300 scripts/summarize_primary_replication.py
```

Known analyzer change immediately before the primary run: `-variant` filtering
was added to run only `vwap_delta_rejection`. The run was verified with:

```bash
gofmt -w main.go types.go
go test ./...
```

Because there is no git history in this workspace, treat the source snapshot as
the best available local version, not as a cryptographically tied commit.

## 4. Canonical Orderflow Transfer With Only MNQ/NQ Files

Yes, copying only MNQ/NQ is intentional when using the `MNQ-NQ` transfer profile.

The helper script is:

```text
scripts/Prepare-PatternMlResearchTransfer.ps1
```

It selects:

```text
MNQ-NQ -> mnq_06-26, nq_06-26
Full   -> mnq_06-26, nq_06-26, es_06-26, mes_06-26
```

However, the helper copies `data/canonical_orderflow_1s/manifest.json` without
filtering it to the chosen profile. Therefore a transfer can contain only MNQ/NQ
CSV files while the manifest still lists ES/MES/GC/MGC files. That is a known
documentation/provenance mismatch, not evidence that the MNQ/NQ CSV transfer is
incomplete.

Use actual files present, or regenerate a filtered manifest on the receiving
machine. Do not treat the copied manifest as a complete file inventory for a
profile-limited transfer.

## 5. SHA-256 Checksums For Canonical Databento

No pre-existing canonical Databento checksum file was found.

I generated one now and included it here:

```text
data/canonical_databento_mnq_2025q1/SHA256SUMS
```

It covers 77 daily `csv.gz` partitions plus `manifest.json`, 78 entries total.
It is generated from the current local canonical Databento files.

## 6. Databento OHLCV-1m 2023-2026 Alternative Strategy Evaluation

Not found for the MNQ/NQ OHLCV-1m 2023-2026 package.

The primary-only Databento Q1 run did not evaluate alternative intraday
strategies. I found the downloaded OHLCV-1m package and metadata, but no local
report showing that it was decoded into an intraday alternative-strategy
tournament.

Separate exploratory daily-bar Databento work does exist under:

```text
data/multi_futures/
reports/multi_futures_baseline_20260613/
reports/multi_futures_comprehensive_20260613/
```

That is not the same as MNQ/NQ 1-minute OHLCV alternatives. Treat it separately
as exploratory cross-market daily research.

## 7. prior_rth_vwap_reclaim In The Next Predeclared Candidate Set

Recommendation: do not include `prior_rth_vwap_reclaim` as a primary
predeclared base candidate.

Reason: it comes from the searched local Ninja sample and is therefore
selection-biased. It can be included only as a quarantined challenger marked
"selected from local v5 / requires fresh prospective clock", or as part of a
clearly declared broad family where the whole family pays a selection penalty.

The safer predeclared base set remains:

```text
raw SFP / stop-sweep reversal
MACD cross
Donchian / volume-delta breakout
RSI reversion
VWAP/delta rejection as frozen benchmark
depth+delta momentum only as Ninja/depth-specific or confirmation-only
```

## 8. Variants To Exclude Or Quarantine

No authoritative blacklist file was found.

Recommended exclusions/quarantine based on the research notes:

- Do not retune `vwap_delta_rejection`; keep it as a frozen rejected benchmark.
- Exclude Apex-reserve-derived variants from IBKR strategy selection. Apex
  reserve was an account constraint, not an edge.
- Quarantine local-sample winners such as `prior_rth_*`, `overnight_*`,
  `value_reclaim`, and `rth_open_*` variants unless they are evaluated as part of
  a predeclared family with selection-bias penalty.
- Do not let depth-dependent variants compete on Databento trade-only data. They
  need independent quote/depth history or must remain Ninja-only confirmation
  research.
- `macd_zero_trend` was noted as needing a NinjaScript zero-line filter before
  live use.

This is a research hygiene recommendation, not a proof that those variants are
bad. The point is to avoid recycling local-search winners as if they were fresh.

## 9. ML / Analog Feature Pipeline Files

Yes, ML/analog research-only files exist and are included in
`reports/pattern_ml_20260612/` and `scripts/`.

Code:

```text
scripts/pattern_ml_research.py
scripts/test_pattern_ml_research.py
```

Research outputs:

```text
reports/pattern_ml_20260612/minute_features.csv.gz
reports/pattern_ml_20260612/decision_features_5m.csv.gz
reports/pattern_ml_20260612/directional_labels.csv.gz
reports/pattern_ml_20260612/model_predictions.csv.gz
reports/pattern_ml_20260612/model_summary.csv
reports/pattern_ml_20260612/analog_neighbors.csv
reports/pattern_ml_20260612/calibration.csv
reports/pattern_ml_20260612/random_controls.csv
reports/pattern_ml_20260612/threshold_selection.csv
reports/pattern_ml_20260612/formula_filter_predictions.csv.gz
reports/pattern_ml_20260612/formula_filter_summary.csv
reports/pattern_ml_20260612/formula_filter_selected_trades.csv
reports/pattern_ml_20260612/formula_filter_threshold_selection.csv
reports/pattern_ml_20260612/leakage_audit.json
reports/pattern_ml_20260612/regime_shift/
reports/pattern_ml_20260612/payoff_asymmetry/
```

These are research-only. They do not authorize live trading or simulation
promotion. They also predate/relate to the local Ninja sample, so treat selected
ML filters as selection-biased unless validated prospectively or on untouched
data.

## Final Cautions

- Do not pool Databento 2025 Q1 and Ninja Apr-Jun 2026 as one homogeneous sample.
- Do not use the stale/full canonical orderflow manifest as proof that ES/MES/GC/MGC
  files were transferred.
- Do not reinterpret the rejected primary as "all strategies fail". It only
  rejects the frozen primary under the independent Q1 replication.
- Do not turn local v5 strongest rows into the next primary without explicitly
  charging for the search that found them.
