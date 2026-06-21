# Strategy Research Handoff Dossier - 2026-06-21

## Purpose

This document is a handoff for a future reasoning model or researcher. It summarizes the work already executed in this project, the strategy families tested, the available evidence, why the candidates failed or were not followed up, and what constraints should govern any next idea.

It is intentionally conservative. The project has produced many apparently promising rows, but the stronger conclusion from the accumulated evidence is:

> **There is currently no active primary validation candidate.**

The next model should not start by trying to rescue the most recently failed candidate. It should first understand the repeated failure modes and then reason from market/financial hypotheses to propose new tests that are genuinely different from what has already failed.

## Current Project State

As of the latest completed iteration:

- Issue #9 selected MNQ 60m Donchian/range breakout with frozen `confluence_score >= 6` as the least weak candidate, but explicitly not tradeable yet.
- Issue #11 tested that Donchian candidate in available-data audit mode and demoted it to `diagnostic_only` because the positive result was too concentrated in the largest winner, best day, and best week.
- Issue #13 re-ranked the families after Donchian's demotion and concluded `collect_specific_data_first`.
- Issue #18 was opened to build a fresh post-selection forward data package. That issue should be understood as data lineage / forward-holdout setup, not as a claim that two extra weeks will discover an edge.

Current family statuses:

| Family | Current status | Practical meaning |
|---|---|---|
| Donchian / range breakout | `diagnostic_only` | Failed concentration gates after being selected as least weak candidate. |
| EMA pullback | `diagnostic_only` | One local 60m monitor is positive, but cross-source evidence conflicts. |
| RSI reversion | `diagnostic_only` | Local evidence looked cleaner than many rows, but independent support is sparse. |
| Prior-day / ORB / VWAP level variants | `diagnostic_only` | Historical hints exist, but exact local frozen confirmation is missing or weak. |
| Bollinger / volatility expansion | `diagnostic_only` | Some Databento rows existed, but no convincing local survivor. |
| MACD / momentum | `diagnostic_only` | Databento rows looked strong; local confirmation failed badly. |
| Raw SFP / order-flow reversal / vwap-delta rejection | `reject` | Independent 2025Q1 replication failed registered gates. |

No family is paper-ready, live-ready, or ready for NinjaTrader/IBKR implementation.

## Data Available and Important Limitations

The project has more than a trivial amount of data. The failure to find a candidate is not because only two weeks are missing.

Key data sources documented in `DATA_INVENTORY.md`:

| Data source | Time span / role | Important limitation |
|---|---|---|
| Ninja/Rithmic canonical order-flow v5 | Approx. 2026-04-01 through 2026-06-08; local 1-second trades/quotes/depth | Local, relatively short; mixed live/replay slices are research evidence, not deterministic parity evidence. |
| Ninja canonical OHLCV 1m | 2026-04-01T11:00:00Z through 2026-06-08T09:57:00Z; MNQ/NQ OHLCV validation | Ends before post-selection forward period; cannot be used as post-2026-06-08 forward data unless rebuilt/imported. |
| Databento OHLCV 1m | 2023-01-02 through 2026-03-31; MNQ/NQ long-history OHLCV | No aggressor delta, quotes, top-book, or depth. Useful for price/volume families only. |
| Databento 2025 Q1 trade/delta canonical | 2025-01-01 through 2025-03-31; independent trade/delta replication | Trade-only, no quotes/depth. Used to reject frozen 1m SFP/vwap-delta primary. |
| Handoff-local Donchian subset | Copied subset under `data/local_canonical/donchian_forward_20260620/` | Useful for available-data audit, not true forward validation. |

The project has historical depth, but the data is heterogeneous. Local Ninja/Rithmic data includes fields unavailable in Databento. Databento long history provides more calendar coverage but cannot validate depth/top-book/order-flow hypotheses that require Ninja/Rithmic features.

## Evidence Standards Used So Far

A strategy family was not rejected merely because one row was negative. It was usually downgraded because one or more of the following failed:

1. **Cross-source agreement:** attractive Databento evidence did not reproduce on local Ninja data, or attractive local evidence did not have historical support.
2. **Concentration robustness:** result depended on one largest winner, one best day, or one best week.
3. **Sample/calendar adequacy:** sample count, number of weeks, or independent windows were too small.
4. **Cost/slippage resilience:** edge faded under modeled cost or slippage.
5. **Net excluding largest winner:** removing the largest winner left the strategy unprofitable or fragile.
6. **Drawdown realism:** drawdown was too high for practical one-contract MNQ research.
7. **Frozen definition:** exact signal definition could not be reconstructed without search/tuning.
8. **Data lineage:** evidence depended on undocumented local paths or reused selection-period data.
9. **Economic plausibility:** some rows looked statistically attractive but did not map clearly to a durable financial mechanism.

These standards should remain in force for future work.

## Chronological Research Map

### 1. Initial pattern / order-flow thesis: SFP and vwap-delta rejection

The early thrust focused on a 1-minute order-flow reversal idea, represented by a frozen MNQ `vwap_delta_rejection` / SFP-style candidate.

The independent 2025 Q1 replication rejected this primary thesis:

- 453 trades across 63 days.
- Net PnL: -$679.22.
- Expectancy: -$1.50.
- Profit factor: 0.89.
- Maximum drawdown: $1,173.06.
- Leave-best-day-out PnL: -$937.28.
- PF without largest winner: 0.86.
- Bootstrap expectancy interval crossed negative.

Reasoning: payoff asymmetry existed, but the total expectancy and PF did not pass. The best-day and largest-winner adjustments were not supportive. This family was moved to `reject`, not merely `diagnostic_only`.

Implication for future work: do not reopen SFP/vwap-delta rejection under a new name unless the new idea is structurally different and has a fresh hypothesis. A minor filter on the rejected reversal thesis is likely data-mining.

### 2. Broader OHLCV discovery and family triage

After the order-flow primary failed, the research broadened into OHLCV families over Databento and local Ninja-derived OHLCV. Families included Donchian/range breakout, MACD/momentum, EMA pullback, RSI reversion, Bollinger/volatility expansion, prior-day/ORB/VWAP level variants, and multi-timeframe selectors.

Issue #9 ranked these families and chose Donchian/range breakout as the least weak family, not because it was strong, but because it had the best combination of:

- broad Databento support;
- simple OHLCV implementation path;
- independently positive local canonical survivor.

At that stage, Donchian was assigned `primary_validation_candidate`, while other families remained diagnostic.

### 3. Donchian / range breakout

**Candidate:** `mnq_60_donchian_confluence_ge6`.

Why it was initially advanced:

- Databento 60m `confluence_score_ge_6`: 587 trades, +$10,193, PF 1.25, max DD $2,799.
- Local frozen survivor: 47 trades, +$1,045, PF 1.22, max DD $1,416, net excluding largest +$551.
- The logic was plain OHLCV and easier to validate than order-flow strategies.

Why it was not trusted even before final demotion:

- Local sample was only 47 trades.
- Largest-winner share was already high at roughly 47.3%.
- Raw local 60m Donchian was weak: 68 trades, +$463, PF 1.05, max DD $3,926.
- The `confluence_score >= 6` selector looked like a potential fragile rescue layer.

Issue #11 attempted validation. Because a true post-selection forward trades-with-context file did not exist, it ran an available-data audit against the frozen registry reference cohort. That audit produced:

- Analysis mode: `available_data_audit`.
- Verdict: `fail_demote_to_diagnostic_only`.
- 47 trades, 9 weeks.
- Net: +$940.
- PF: 1.20.
- Max DD: $1,438.
- Largest-winner share: 52.4%.
- Best-day share: 83.0%.
- Best-week share: 117.1%.
- Net excluding largest: +$448.

Reasoning: nominal profitability did not matter because the result was too concentrated. A strategy that relies on one best week explaining more than the total net result is not robust enough for a validation lane.

Decision: Donchian was demoted from `primary_validation_candidate` to `diagnostic_only`.

What would be required to reconsider Donchian:

- A true post-selection forward cohort, not the same available-data audit slice.
- Enough trades and weeks.
- Largest-winner share below 50%.
- Best-day and best-week concentration below 50%.
- Positive net excluding largest winner.
- No retuning of `confluence_score` or breakout logic.

### 4. EMA pullback

EMA produced the most persistent diagnostic signal, but not enough for promotion.

Issue #7 reconciled a mismatch:

- Long-history Databento evidence favored 15m EMA pullback with down-trend filters.
- Local Ninja evidence favored raw 60m EMA behavior.

Issue #8 froze two EMA monitors:

1. `local_raw_60m_ema_pullback`.
2. `databento_style_15m_ema_month_or_week_down`.

Results:

- `local_raw_60m_ema_pullback`: 66 trades, 9 weeks, +$2,478, PF 1.31, max DD $1,015, largest-winner share 36.4%, net excluding largest +$1,575. It stayed positive under 1 and 2 ticks per side slippage.
- `databento_style_15m_ema_month_or_week_down`: 22 trades, 3 weeks, -$1,287, PF 0.44, max DD $1,404, net excluding largest -$1,697. It failed across slippage scenarios.

Why not followed up as a primary candidate:

- The local signal and Databento signal disagreed on timeframe/filter regime.
- The Databento-style monitor failed locally.
- Databento raw 15m and raw 60m EMA support was weak/negative in prior triage.
- The local 60m monitor is reused baseline evidence, not fresh forward validation.

Decision: keep `local_raw_60m_ema_pullback` only as a frozen diagnostic monitor. Do not use it for paper trading or implementation.

What a future model should consider:

- EMA might be a **regime descriptor** rather than an entry strategy.
- The question may be whether EMA pullback identifies local trend persistence periods, not whether it is a standalone edge.
- Any future EMA use should be pre-registered as a feature/hypothesis and tested against independent forward periods.

### 5. MACD / momentum

MACD looked attractive in Databento but failed local confirmation.

Evidence for:

- Databento examples included `tf60_rsi_align_aligned`: 190 trades, +$8,989, PF 1.72, max DD $1,227.
- Another Databento selector reported 156 trades, +$6,236, PF 1.65, max DD $1,763.

Evidence against:

- Raw local MNQ 60m MACD: 63 trades, -$4,523, PF 0.54, max DD $5,848.
- Tested frozen local `mnq_60_macd_tf60_rsi_aligned`: 11 trades, -$587, PF 0.62.

Reasoning: this is a clear cross-source failure. A model should not infer that a strong historical Databento row can be promoted when the local canonical data contradicts it so strongly.

Decision: `diagnostic_only`. Do not spend near-term validation budget unless new non-selection local evidence materially contradicts the old local failure.

### 6. RSI reversion

RSI is not rejected, but it is not validated.

Evidence for:

- Local strict raw combo: MNQ 30m RSI reversion.
- 39 trades.
- Net +$1,514.
- PF 1.19.
- Max DD $1,149.
- Largest-winner share 29.1%.
- Net excluding largest +$1,074.

Evidence against:

- Weak Databento support: only 3 relaxed rows and 0 practical/strict rows in the relevant triage.
- Calendar coverage and best-day/week concentration were not fully captured in the handoff matrix.
- No frozen forward monitor exists.
- Exact definition may need recovery from local evidence.

Reasoning: RSI is one of the cleaner local hints, but local-only selection evidence is not enough. It may represent a short-lived local regime or selection-period fit. It should not be promoted without independent or post-selection support.

Decision: `diagnostic_only`.

Future handling:

- Recover the exact frozen RSI definition only if it can be done without parameter search.
- Test it on a clean post-selection package.
- If Databento remains sparse, the model should explain why a local-only hypothesis is still financially plausible, or discard it.

### 7. Prior-day / ORB / VWAP level variants

This family contains several structurally plausible ideas: opening range behavior, prior-day high/low rejection, VWAP reclaim, and level-based continuation/reversal. It did not become a candidate because the evidence did not become exact and portable.

Evidence for:

- Databento had practical rows, including 15m `prior_day_rejection` with month-trend-flat: 406 trades, +$4,923, PF 1.34, DD $1,080.
- Some ORB rows were positive in Databento.

Evidence against:

- Local raw confirmation is missing or weak.
- ORB holdout samples were tiny.
- VWAP reclaim had weak split behavior.
- The frozen 1m `vwap_delta_rejection` primary, which belongs to the broader VWAP/order-flow reversal neighborhood, was rejected.
- Exact frozen definitions are not currently available for a clean local validation lane.

Decision: `diagnostic_only`.

Potential value for future reasoning:

- This family may be worth rethinking from first principles: session structure, opening auction imbalance, prior-day inventory, volatility expansion after failed breaks, or trend-day context.
- But the next model must not simply pick the best Databento level row. It should propose a financially grounded mechanism and specify a frozen definition before any test.

### 8. Bollinger / volatility expansion

Evidence for:

- Broader audit found 37 relaxed Databento rows and 3 practical/strict rows.

Evidence against:

- No convincing local raw survivor.
- No stable cross-source candidate.
- Some local Bollinger candidates were tiny-sample or largest-winner dependent.
- No exact frozen candidate is ready.

Decision: `diagnostic_only`.

Future handling:

- Treat Bollinger/volatility as a possible state variable, not necessarily as an entry signal.
- A future test should distinguish volatility compression/expansion regimes from mean-reversion bands.
- Do not advance without a frozen candidate and local plus independent support.

### 9. Multi-timeframe selectors and regime filters

Many of the attractive rows depended on selectors such as week trend, month trend, confluence score, RSI alignment, range context, or timeframe alignment.

These filters are not inherently invalid. However, they are dangerous because they can manufacture a profitable row by slicing data until a regime appears.

Observed pattern:

- Donchian needed `confluence_score >= 6` to look best.
- EMA looked different across Databento and local data depending on timeframe and trend filters.
- MACD had impressive Databento context-filter rows but failed locally.

Decision: regime filters are allowed only when:

- the financial mechanism is stated before testing;
- the filter is simple and stable;
- the same filter is evaluated across sources/windows;
- promotion depends on robustness after removing largest winner/day/week;
- the filter is not tuned after seeing the result.

## Repeated Failure Modes Across the Project

### Failure Mode 1: Attractive historical rows that do not reproduce locally

MACD is the clearest example. Databento rows had strong net/PF/DD, but local MNQ 60m MACD was deeply negative. This points to either regime specificity, data/source differences, or overfit selector discovery.

### Failure Mode 2: Attractive local rows with weak historical support

EMA and RSI fit here. Local EMA 60m and local RSI 30m had positive evidence, but either cross-source support failed or long-history support was sparse.

### Failure Mode 3: Nominally positive results dominated by one event

Donchian is the clearest example. It remained positive, but its result failed concentration gates. This is why largest-winner share, best-day share, and best-week share must be first-class metrics in future work.

### Failure Mode 4: Selection-period evidence reused as validation

Several rounds had to distinguish available-data audit from true forward validation. A future model must preserve that distinction. A positive reused local cohort is not forward evidence.

### Failure Mode 5: Frozen definition missing

Prior-day/ORB/VWAP, Bollinger, and RSI cannot be promoted unless exact definitions can be recovered. If a worker has to infer parameters, the result becomes new discovery, not validation.

### Failure Mode 6: Data source mismatch

Databento OHLCV is long and clean for price/volume but lacks local order-flow/depth fields. Ninja/Rithmic local data has richer microstructure fields but a shorter local window. A hypothesis must specify which data source can actually validate it.

## What Another Model Should Not Do

Do not:

- start from the assumption that a strategy is hidden in the existing best rows;
- retune Donchian's confluence score;
- add filters to rescue MACD or EMA without a pre-stated mechanism;
- promote local-only RSI merely because it is the least bad remaining row;
- revisit SFP/vwap-delta rejection without a structurally new hypothesis;
- treat two additional weeks of post-selection data as likely to prove an edge;
- move toward NinjaTrader order execution, IBKR, paper trading, or live trading.

## What Another Model Could Usefully Reason About

The next model should reason from financial structure rather than from score tables. Useful questions include:

1. **What market mechanism was each failed family trying to capture?**
   - Donchian: range expansion / breakout continuation.
   - EMA: trend persistence / pullback continuation.
   - MACD: momentum regime continuation.
   - RSI: short-horizon exhaustion / reversion.
   - ORB/prior-day/VWAP: session-level liquidity, inventory, and reference-price reaction.
   - SFP/vwap-delta: failed auction / trapped participants / delta-price divergence.

2. **Which mechanisms are plausible for MNQ specifically?**
   MNQ is retail-heavy, highly coupled to NQ, sensitive to US equity session structure, macro releases, and index/mega-cap flow. Any new hypothesis should explain why MNQ should show the effect after costs.

3. **Which features were missing from long-history validation?**
   Databento OHLCV cannot validate quote/depth features. If the new idea relies on top-book, spread, depth imbalance, or aggressor flow, the evidence must come from Ninja/Rithmic or a comparable source.

4. **Which failure modes suggest a new direction?**
   - If breakout fails due to concentration, maybe trend continuation requires volatility/session context.
   - If EMA local-only works but Databento-style fails, maybe trend definitions need to be market-regime rather than moving-average based.
   - If RSI local-only works but lacks historical support, maybe mean reversion is regime-specific and should be conditioned on volatility/time-of-day/news avoidance.
   - If ORB/prior-day has Databento hints but weak local confirmation, maybe exact session definitions or contract roll/session alignment matter.

5. **What would falsify the next idea quickly?**
   Every new idea should include a pre-defined failure gate: net <= 0, PF < 1 under slippage, largest-winner/day/week concentration, no net excluding largest, or non-reproducibility across data sources.

## Recommended Structure for Future Hypotheses

Any next test proposal should be written in this format:

```text
Hypothesis:
  What market behavior should exist, and why?

Instrument / session:
  MNQ first? NQ confirmation? RTH only? Globex? Event exclusions?

Data required:
  OHLCV only, trade/delta, quote/top-book/depth, or replay parity?

Frozen signal definition:
  Exact entry, exit, filters, timeframe, costs, and slippage.

Why this is not already tested:
  Explain how it differs from Donchian, EMA, MACD, RSI, Bollinger, ORB/VWAP, or SFP variants above.

Validation plan:
  Source windows, selection window, holdout/forward window, minimum trades/weeks.

Failure gates:
  Net, PF, DD, largest winner, best day/week, net excluding largest, source-lineage checks.

Promotion ceiling:
  Diagnostic? Research monitor? Primary validation candidate? Never paper/live from one run.
```

## Current Best Next Step

If the goal is a clean continuation of the current process, the next execution step remains Issue #18: create a post-selection forward package. However, this should not be interpreted as alpha discovery. It is only a clean boundary for later monitoring and evidence collection.

If the goal is to find genuinely new candidate ideas, a future model should read this dossier and propose a small number of financially motivated hypotheses that are materially different from the failed families. Those hypotheses should then be converted into tightly scoped issues with explicit falsification gates.

## Key Artifact Index

| Artifact | Role |
|---|---|
| `DATA_INVENTORY.md` | Data source map and portability constraints. |
| `STRATEGY_FAMILY_TRIAGE_20260620.md` | Issue #9 family ranking that initially selected Donchian. |
| `reports/strategy_family_triage_20260620/family_rankings.csv` | Machine-readable Issue #9 ranking. |
| `reports/donchian_forward_validation_20260620/VERDICT.md` | Issue #11 Donchian demotion. |
| `reports/donchian_forward_validation_20260620/donchian_forward_summary.csv` | Donchian concentration/cost metrics. |
| `reports/ema_forward_monitor_20260620/VERDICT.md` | Issue #8 EMA frozen-monitor decision. |
| `reports/mnq_2025q1_primary_replication/VERDICT.md` | Independent SFP/vwap-delta rejection. |
| `reports/next_iteration_retriage_20260621/VERDICT.md` | Issue #13 no-candidate / collect-data-first verdict. |
| `reports/next_iteration_retriage_20260621/candidate_evidence_matrix.csv` | Compact family-by-family evidence matrix. |
| `reports/next_iteration_retriage_20260621/data_gap_matrix.csv` | Current data gaps and why promotion is blocked. |

## Bottom Line

The project has not failed because it lacked two more weeks of data. It has failed to produce a candidate because the tested families did not survive conservative evidence standards.

The main lessons are:

- historical profitability rows are not enough;
- cross-source agreement matters;
- concentration in one winner/day/week is a major red flag;
- local-only evidence needs independent support;
- order-flow ideas require matching order-flow data, not OHLCV substitutes;
- exact frozen definitions and source lineage are mandatory.

A future model should use this document as a map of what has already been ruled out, what remains merely diagnostic, and what kind of financial hypothesis would be meaningfully new.
