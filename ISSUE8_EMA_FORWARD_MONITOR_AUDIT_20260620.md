# Issue #8 EMA Forward Monitor Audit - 2026-06-20

GitHub issue: https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/8

Latest controlling comment audited:
https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/8#issuecomment-4756441646

## Scope

Review-only audit of the Issue #8 outputs. No EMA tuning, no strategy discovery,
no NinjaTrader code, no broker integration, and no trading recommendation.

Files reviewed:

- `AGENTS.md`
- `scripts/run_ema_forward_monitor.py`
- `EMA_FORWARD_MONITORS_20260620.md`
- `reports/ema_forward_monitor_20260620/VERDICT.md`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_config.json`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.csv`
- `reports/ema_forward_monitor_20260620/ema_forward_monitor_summary.json`
- `reports/ema_forward_monitor_20260620/join_checks.csv`

## Pre-Audit Fix Applied

I found and fixed one portability issue before finalizing this audit:

- `scripts/run_ema_forward_monitor.py` previously wrote resolved local absolute
  paths into `VERDICT.md` and `ema_forward_monitor_config.json`.
- It now writes repo-relative paths and adds
  `cohort_label = existing_local_baseline_not_newly_appended_forward`.
- The report was regenerated with `scripts/run_ema_forward_monitor.py --force`.

## Check Results

1. Are all generated artifacts committed or ready to commit?

PASS, with one repo-convention note. The source artifacts are untracked and ready
to add:

- `EMA_FORWARD_MONITORS_20260620.md`
- `scripts/run_ema_forward_monitor.py`
- `ISSUE8_EMA_FORWARD_MONITOR_AUDIT_20260620.md`

The generated report folder exists, but `reports/` is ignored by `.gitignore`,
so those files require `git add -f reports/ema_forward_monitor_20260620/...` if
the repo wants report artifacts committed.

2. Are report paths repo-relative and portable, rather than local absolute paths
where avoidable?

PASS after the fix. `ema_forward_monitor_config.json` lines 5-7 now use
repo-relative paths, and `VERDICT.md` now reports the same repo-relative input
paths.

3. Does the runner use exactly the two frozen monitors from Issue #8, with no
hidden variant search or parameter changes?

PASS. The runner defines only two monitors in
`scripts/run_ema_forward_monitor.py` lines 190-220:

- `local_raw_60m_ema_pullback`
- `databento_style_15m_ema_month_or_week_down`

It filters only by root/timeframe/variant and the explicit 15m
`month_trend == down OR week_trend == down` condition. There is no variant
search loop.

4. Are the filter definitions, thresholds, cost assumptions, slippage scenarios,
and cadence encoded in a machine-readable config?

PASS. `ema_forward_monitor_config.json` includes:

- filters and thresholds in `monitors`
- base cost and slippage sensitivity in `cost_model`
- cadence and rerun rule in `cadence`
- issue link and generated-by metadata

See `scripts/run_ema_forward_monitor.py` lines 396-429 and generated config
lines 10-61.

5. Do join checks verify root, timeframe, variant, and entry-time consistency,
not only trade IDs?

PASS. `scripts/run_ema_forward_monitor.py` lines 148-179 checks
`root/timeframe/variant/entry_time` duplicates and context-to-raw matches.
`join_checks.csv` lines 2-6 all pass, including `context_to_raw_key_match`.

6. Is the current cohort clearly labeled as existing/local baseline evidence,
not a true newly appended forward period unless such new data exists?

PASS after the fix. `ema_forward_monitor_config.json` line 10 labels the cohort
as `existing_local_baseline_not_newly_appended_forward`; `VERDICT.md` states
the cohort is the currently available existing local baseline.

7. Is the recommendation supported: keep only `local_raw_60m_ema_pullback` as an
active frozen diagnostic monitor and keep EMA as `diagnostic_only`?

PASS. `VERDICT.md` lines 43-56 show:

- `local_raw_60m_ema_pullback`: 66 trades, 9 weeks, +$2,478 baseline, PF 1.31,
  max DD $1,015, largest-winner share 36.4%, net ex-largest +$1,575; still
  passes with 1 and 2 slippage ticks per side.
- `databento_style_15m_ema_month_or_week_down`: 22 trades, 3 weeks, -$1,287
  baseline, PF 0.44, net ex-largest -$1,697; fails sample size, coverage,
  net/PF, and outlier-dependence checks.

`VERDICT.md` lines 59-62 correctly refuses promotion to `research_monitor`,
paper, or live trading.

## Required Fixes Before Closing

None remaining after the path/cohort-label fix and regeneration.

## Recommendation

Close Issue #8 as complete.

Do not create a strategy-discovery or implementation follow-up from this issue.
The only natural follow-up is operational: rerun
`scripts/run_ema_forward_monitor.py` when explicitly newly appended local
canonical data exists. Until then, EMA remains `diagnostic_only`.
