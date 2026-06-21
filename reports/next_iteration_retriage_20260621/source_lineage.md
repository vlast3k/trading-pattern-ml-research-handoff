# Source Lineage

Generated: 2026-06-21

This retriage used repo-local handoff artifacts and inventory-relative references only. It did not read hidden absolute data paths except where `DATA_INVENTORY.md` documents external raw NinjaTrader locations as provenance.

## Repo-Local Inputs

| Role | Path | Use |
|---|---|---|
| Canonical plan | `NEXT_ITERATION_PLAN_20260621.md` | Issue #13 product framing |
| Prior family triage | `STRATEGY_FAMILY_TRIAGE_20260620.md` | Baseline family ranking before Donchian demotion |
| Prior ranking CSV | `reports/strategy_family_triage_20260620/family_rankings.csv` | Machine-readable prior evidence |
| Data inventory | `DATA_INVENTORY.md` | Dataset availability and portability rules |
| Donchian verdict | `reports/donchian_forward_validation_20260620/VERDICT.md` | Demotion evidence |
| Donchian summary | `reports/donchian_forward_validation_20260620/donchian_forward_summary.csv` | Concentration and cost metrics |
| Donchian lineage | `reports/donchian_forward_validation_20260620/source_lineage.md` | Available-data audit source status |
| EMA report | `reports/ema_forward_monitor_20260620/VERDICT.md` | EMA diagnostic status |
| EMA summary | `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.csv` | EMA cost/slippage metrics |
| EMA audit note | `ISSUE8_EMA_FORWARD_MONITOR_AUDIT_20260620.md` | EMA monitor audit context |
| SFP primary replication | `reports/mnq_2025q1_primary_replication/VERDICT.md` | Rejected order-flow reversal evidence |
| Pattern ML report | `reports/pattern_ml_20260612/VERDICT.md` | Prior pattern-ML/SFP context |
| Databento primary verdict | `reports/pattern_ml_20260612/DATABENTO_2025Q1_DOWNLOAD_AND_PRIMARY_VERDICT.md` | Independent 2025Q1 replication context |

## Inventory-Relative Data Sources Referenced

| Dataset | Inventory path | Role |
|---|---|---|
| Current Ninja/Rithmic order-flow v5 | `../trading/data/canonical_orderflow_1s/` | Current local order-flow/depth source through the existing research window; not directly reprocessed here |
| Current Ninja OHLCV 1m | `../trading/data/ninja_canonical_ohlcv_1m/` | Existing selection-window OHLCV source only; `DATA_INVENTORY.md` records it ending at `2026-06-08T09:57:00+00:00`, so it cannot supply post-selection forward bars unless rebuilt/imported first |
| Raw Ninja exports/replay | `C:\Users\vlast\Documents\NinjaTrader 8\export\`; `C:\Users\vlast\Documents\NinjaTrader 8\db\replay\` | Inventory-documented raw provenance for rebuilding/importing a fresh post-`2026-06-08` canonical source |
| Databento OHLCV 1m | `../trading/data/databento_ohlcv_1m/` | Long-history OHLCV context from prior reports, not newly queried here |
| Databento Q1 trade/delta canonical | `../trading/2026.08.17 - trading transfer/canonical_databento_mnq_2025q1/` | Independent 2025Q1 replication source from prior reports |

## Reproducibility Note

The required next package should be created under:

```text
data/local_canonical/post_selection_forward_20260609_plus/
```

Large payloads may remain ignored, but the package must include `IMPORT_MANIFEST.json` and `source_lineage.md` so the next worker can verify paths, row counts, timestamp spans, checksums, and source provenance.

Important: the package must be built from a fresh canonical OHLCV/order-flow source that extends beyond `2026-06-08`. The existing `../trading/data/ninja_canonical_ohlcv_1m/` source is stale for this purpose and should be treated only as selection-window evidence unless it is explicitly rebuilt/imported and documented.

