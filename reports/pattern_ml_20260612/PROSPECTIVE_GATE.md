# Frozen Prospective Gate

Frozen after the regime-shift diagnosis on June 12, 2026.

## Candidate

- Formula: exact existing MNQ 1-minute `vwap_delta_rejection`.
- Use every formula signal. No long-only, high-volatility, provenance, ML, or session filter.
- Research and paper validation only. No unattended or real-money trading.

## Start

- Prospective observation begins after trading day `2026-06-12`, when this gate was frozen.
- The already-visible June 8 result is retrospective and does not count toward the gate.
- Do not use any data through June 12 to retune thresholds or select filters.

## Minimum Evidence Before Another Promotion Review

- At least 50 new formula trades.
- At least 20 new substantial trading days.
- Include both long and short signals.
- Report results separately for live and replay provenance when available.

This is only an interim failure screen. A decision-grade review requires:

- at least 200 non-overlapping new formula trades;
- at least 60 substantial prospective trading days;
- at least two MNQ contract/roll periods;
- trading-day bootstrap 95% lower bounds above zero expectancy and profit factor `1.0`.

## Review Conditions

- Average winner / average loser payoff ratio of at least `1.30`.
- Total winning dollars / total losing dollars profit factor of at least `1.20`.
- Observed win rate at least 3 percentage points above the break-even win rate implied by the payoff ratio.
- Positive expectancy per trade after the modeled `$1.24` IBKR round-turn fees and one
  MNQ tick of slippage per side, `$2.24` total.
- Profit factor of at least `1.00` after removing the largest winner.
- Positive PnL after removing the best day.
- Positive or acceptably flat performance in both halves of the prospective window.
- No single direction, volatility state, session, or provenance source explains all profit.
- Maximum drawdown remains compatible with the paper-trading risk objective.

Until these conditions are met, the frozen verdict remains: no strategy is approved for unattended or real-money trading.

## Monitor Command

After the exact formula trade report is refreshed with new canonical data:

```bash
.venv/bin/python scripts/monitor_formula_prospective.py
```

The frozen monitor writes `reports/pattern_ml_20260612/prospective_monitor/STATUS.md`.
