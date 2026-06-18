# Databento 2025 Q1 Download And Primary Verdict

Date completed: June 13, 2026

## Download

The user-approved recent replication package completed successfully:

| Request | Actual cost | Records | Download package |
|---|---:|---:|---:|
| MNQ trades, January-March 2025 | $78.51 | 62,725,320 | 1.02 GB |
| MNQ+NQ OHLCV-1m, January 2023-March 2026 | $13.02 | 3,566,547 | 0.05 GB |
| MNQ+NQ definitions, January 2023-March 2026 | $0.02 | 37,138 | 0.002 GB |
| **Total** | **$91.55** |  | approximately **1.0 GB** on disk |

Files are under `data/databento_2025q1_replication`. SHA-256 checksums are stored in
`data/databento_2025q1_replication/SHA256SUMS`.

If the account began with `$125` free credit and the earlier `$4.52` package was the
only other billed request, the implied remaining credit is approximately `$28.93`.
The Databento API does not expose the actual account-credit balance, so the portal is
authoritative.

## Conversion

The primary replication uses only outright MNQ contracts. Each UTC day selects the
outright contract with the highest total MNQ trade volume. This produced 77 daily
canonical partitions and used MNQH5 and MNQM5.

Databento trade-side semantics were verified before the published run:

- `A`: sell aggressor, mapped to `sell_volume`;
- `B`: buy aggressor, mapped to `buy_volume`;
- `N`: unknown.

Known aggressor-side volume coverage is `99.986%`; unknown volume is `0.014%`.

An initial unpublished conversion had A/B reversed. It was detected against the
official Databento schema documentation, deleted, rebuilt, and never used for the
published verdict.

## Frozen Primary-Only Test

The analyzer was restricted to:

- MNQ 1-minute `vwap_delta_rejection`;
- one open position at a time;
- `$2.24` modeled round-turn cost;
- no alternative strategy outcomes.

Results:

| Metric | Result |
|---|---:|
| Non-overlapping trades | 453 |
| Trading days | 63 |
| Long / short | 220 / 233 |
| Net PnL | **-$679.22** |
| Expectancy | **-$1.50** |
| Profit factor | **0.89** |
| Payoff ratio | 1.51 |
| Maximum drawdown | $1,173.06 |
| Leave-best-day-out PnL | -$937.28 |
| PF without largest winner | 0.86 |
| First / second half | -$795.74 / +$116.52 |
| Bootstrap expectancy 95% interval | -$4.50 to +$1.77 |
| Bootstrap PF 95% interval | 0.69 to 1.15 |

## Verdict

**Reject the current frozen MNQ 1-minute `vwap_delta_rejection` primary.**

The payoff asymmetry survived, but the win rate did not. The independent sample fails
profit factor, expectancy, leave-best-day-out, largest-winner removal, chronological
stability, and trading-day bootstrap gates.

This result should not be tuned away. The downloaded one-minute bars can now be used
as development evidence for price/volume alternatives, but any newly selected strategy
will require another untouched holdout or prospective validation.
