# 2025 Q1 Frozen Primary Replication

**Verdict: does not pass the registered statistical gates.**

This is an independent historical replication of only the frozen MNQ 1-minute `vwap_delta_rejection` candidate. It uses the dominant outright MNQ contract per UTC day, one open position at a time, and the `$2.24` modeled round-turn cost.

- Trades / days: `453` / `63`.
- Long / short: `220` / `233`.
- Net PnL: `$-679.22`; expectancy `$-1.50`.
- Profit factor: `0.89`; payoff ratio `1.51`.
- Maximum drawdown: `$1,173.06`; worst day `$-325.88`.
- Leave-best-day-out PnL: `$-937.28`.
- Profit factor without largest winner: `0.86`.
- First / second half PnL: `$-795.74` / `$+116.52`.
- Trading-day bootstrap expectancy 95% interval: `$-4.50` to `$+1.77`.
- Trading-day bootstrap PF 95% interval: `0.69` to `1.15`.

This result must remain separate from prospective evidence. Alternative-strategy outcomes have not been generated in this primary-only analyzer run.
