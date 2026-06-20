# Strategy Family Triage - 2026-06-20

Active issue: [#9 Rank strategy families for next practical validation](https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/9)

## Verdict

**Primary recommendation: advance one family to a focused validation task.**

Advance **MNQ 60m Donchian/range breakout with the frozen `confluence_score >= 6` selector** as the next practical validation candidate. This is **not tradeable yet**. It is the least weak candidate because it is the only family that currently has broad Databento support, a simple OHLCV implementation path, and an independently positive local canonical survivor.

Candidate ID for the next task:

- Family: `donchian_breakout`
- Frozen candidate: `mnq_60_donchian_confluence_ge6`
- Entry model: 60m Donchian/range breakout
- Selector: `confluence_score >= 6`
- Instrument: MNQ first, one contract
- Status: `primary_validation_candidate`

## Evidence Read

- `reports/mnq_2025q1_primary_replication/VERDICT.md`
- `reports/mnq_2025q1_primary_replication/summary.json`
- `reports/pattern_ml_20260612/DATABENTO_2025Q1_DOWNLOAD_AND_PRIMARY_VERDICT.md`
- `reports/ema_forward_monitor_20260620/VERDICT.md`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_config.json`
- `reports/ema_forward_monitor_20260620/join_checks.csv`
- Parallel local research notes from the original trading workspace:
  - `BROADER_STRATEGY_DISCOVERY_20260619.md`
  - `OHLCV_META_SELECTOR_RESEARCH_20260619.md`
  - `EMA_PULLBACK_RECONCILIATION_20260619.md`
  - `reports/broader_strategy_discovery_20260619/family_gate_summary.csv`
  - `reports/broader_strategy_discovery_20260619/databento_practical_selector_rows.csv`
  - `reports/broader_strategy_discovery_20260619/local_positive_raw_combos.csv`
  - `reports/broader_strategy_discovery_20260619/local_strict_raw_combos.csv`

No new parameter search, data download, or platform code was run for this triage.

## Ranked Families

| Rank | Family | Status | Strongest Candidate | Evidence For | Reason Not To Trust |
|---:|---|---|---|---|---|
| 1 | Donchian / range breakout | `primary_validation_candidate` | `mnq_60_donchian_confluence_ge6` | Databento 60m `confluence_score_ge_6`: 587 trades, +$10,193, PF 1.25, max DD $2,799. Local frozen survivor: 47 trades, +$1,045, PF 1.22, max DD $1,416, net ex-largest +$551. Formula is plain OHLCV and easier to validate than order-flow variants. | Local sample is only 47 trades and largest-winner share is still 47.3%. Raw local 60m Donchian was weak: 68 trades, +$463, PF 1.05, max DD $3,926. This needs true frozen forward/new-period validation. |
| 2 | MACD / momentum with multi-timeframe selectors | `diagnostic_only` | MNQ 60m `macd_cross` with week/range/RSI context | Databento had strong rows, e.g. `tf60_rsi_align_aligned`: 190 trades, +$8,989, PF 1.72, max DD $1,227; `best_combo_week_trend_net_t50_pf1.05_nofallback`: 156 trades, +$6,236, PF 1.65, max DD $1,763. | Local confirmation failed. Raw local MNQ 60m MACD was 63 trades, -$4,523, PF 0.54, max DD $5,848; tested frozen local `mnq_60_macd_tf60_rsi_aligned` was 11 trades, -$587, PF 0.62. Keep as reference only. |
| 3 | EMA pullback | `diagnostic_only` | `local_raw_60m_ema_pullback` frozen monitor | Local raw 60m monitor passed the existing baseline: 66 trades, +$2,478, PF 1.31, max DD $1,015, largest-winner share 36.4%, net ex-largest +$1,575. Join checks passed for the Issue #8 monitor artifacts. | Cross-source mismatch. Databento-style 15m month/week-down monitor failed locally: 22 trades, -$1,287, PF 0.44. Databento raw 15m and 60m EMA were negative. Keep frozen as diagnostic only, not as a primary paper candidate. |
| 4 | RSI reversion | `diagnostic_only` | MNQ 30m raw RSI reversion | Local strict raw combo was relatively clean: 30m RSI reversion had 39 trades, +$1,514, PF 1.19, max DD $1,149, largest-winner share 29.1%, net ex-largest +$1,074. | Weak Databento support: family gate summary showed 3 relaxed Databento rows but 0 practical/strict rows. Too sparse for a practical validation track until it has independent historical support. |
| 5 | Prior-day / ORB / VWAP level variants | `diagnostic_only` | Prior-day rejection and ORB rows only as diagnostics | Some Databento practical rows exist, e.g. 15m `prior_day_rejection` month-trend-flat: 406 trades, +$4,923, PF 1.34, DD $1,080; 30m ORB rows were positive in Databento. | Local raw confirmation is missing or largest-winner dependent. ORB holdout samples were tiny. VWAP reclaim had weak split behavior. The frozen 1m `vwap_delta_rejection` primary was already rejected. |
| 6 | Bollinger / volatility expansion | `diagnostic_only` | None ready | Databento found some strict practical rows: 37 relaxed, 3 practical, 3 strict in the broader family audit. | No convincing local raw survivor and no stable cross-source candidate. Do not spend near-term validation budget here unless new forward data changes the picture. |
| 7 | Raw SFP / order-flow reversal primary | `reject` | Frozen MNQ 1m `vwap_delta_rejection` / SFP-style reversal | The research question was tested directly in the 2025Q1 replication. Payoff asymmetry survived, but win rate failed. | Frozen primary rejected: 453 trades across 63 days, -$679.22, PF 0.89, max DD $1,173.06; leave-best-day-out -$937.28; PF without largest winner 0.86; bootstrap expectancy crossed negative. Do not continue near-term rescue work. |

Machine-readable ranking: `reports/strategy_family_triage_20260620/family_rankings.csv`.

## Families To Stop Near-Term

- **Frozen 1m `vwap_delta_rejection` / SFP primary:** rejected by the independent 2025Q1 replication.
- **Raw SFP rescue:** too little robust evidence and too close to the rejected reversal thesis.
- **Standalone MACD promotion:** strong historical rows exist, but local confirmation failed.
- **Standalone EMA promotion:** local 60m monitor is interesting, but cross-source formula/timeframe mismatch blocks promotion.
- **Standalone Bollinger, ORB, VWAP reclaim, prior-day rescue:** keep only as diagnostics until frozen forward evidence or a separately specified issue justifies them.

## Next Focused Validation Issue

Open a focused validation issue for:

**Validate frozen MNQ 60m Donchian `confluence_score >= 6` on newly appended forward/local data.**

### Exact Cohort

- Instrument: MNQ
- Timeframe: 60m
- Candidate: `donchian_breakout`
- Selector: frozen `confluence_score >= 6`
- Trade size: one MNQ contract
- Data: data not used to define or choose the candidate, preferably newly appended local canonical OHLCV after the existing June research window.
- Data location: all validation inputs must live under documented repo-relative ignored paths, for example `data/local_canonical/...` or `data/databento/...`. Scripts/configs may use documented environment variables, but they must not depend on ad hoc absolute local paths.
- Minimum observation target: at least 4 calendar weeks and at least 30 trades before judging; if fewer than 30 trades after 6 weeks, report as under-sampled rather than pass/fail.

### Data Reproducibility Gate

The next Donchian validation is **incomplete** unless it emits a `source_lineage.md` or equivalent manifest containing every input path as repo-relative metadata:

- repo-relative input path
- whether the input is committed or intentionally ignored
- `.gitignore` coverage confirmation for large/proprietary uncommitted data
- file size
- row count where applicable
- first and last timestamp where applicable
- SHA-256 or equivalent checksum when practical
- documented copy, symlink, or import step if the source originated outside the repo tree

Validation should fail or be marked incomplete if required data remains outside the repo checkout with no documented repo-relative import/symlink/copy step.

### Validation Gates

Pass only if all hold:

- The data reproducibility gate above passes.
- Net profit after stated commissions and fees is positive.
- PF is at least 1.10 at baseline cost and at least 1.05 under 2 ticks per side slippage.
- Max drawdown is no worse than $2,500 for one MNQ contract.
- Largest-winner share is below 50%, and net excluding largest winner remains positive.
- No single week or day explains the majority of the result.
- Entry/exit timestamps, session assumptions, and cost assumptions are written in the artifact.

### Failure Conditions

Reject or demote if any hold:

- Net <= 0 after costs.
- PF < 1.0 under 2 ticks per side slippage.
- Max drawdown > $2,500 before enough positive expectancy is observed.
- Largest-winner share >= 50% or net excluding largest winner <= 0.
- Forward trades materially disagree with the frozen formula or selector definition.
- Required data inputs are outside repo-relative documented `data/...` paths, or no lineage/checksum manifest is produced.

### Next Worker Task

Build a frozen forward monitor for `mnq_60_donchian_confluence_ge6`, mirroring the Issue #8 EMA monitor discipline:

1. Freeze the candidate definition in a small config/report artifact.
2. Place or reference all required uncommitted large inputs under repo-relative ignored `data/...` paths.
3. Emit `source_lineage.md` with input paths, file sizes, row counts, timestamp spans, checksums where practical, and ignore/import status.
4. Join only the required local canonical OHLCV/new-period inputs.
5. Emit trade-level CSV plus summary metrics.
6. Emit join/timeframe/session checks.
7. Write a verdict without retuning.
8. Keep the status at `primary_validation_candidate` unless the gates above are actually met on forward data.

## Acceptance Criteria

- PASS: All families requested in Issue #9 are ranked.
- PASS: Each family has a conservative status.
- PASS: Exactly one primary recommendation is made.
- PASS: The recommendation includes candidate ID, cohort, metric gates, failure conditions, and next worker task.
- PASS: The next validation task now includes a repo-relative data-location and source-lineage reproducibility gate.
- RISK: This triage depends partly on local parallel-research artifacts outside this handoff repository; the key numbers are copied here so the decision remains reviewable.
