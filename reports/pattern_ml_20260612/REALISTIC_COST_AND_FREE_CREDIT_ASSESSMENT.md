# Realistic IBKR Cost Simulations And Databento Credit Plan

Date: June 13, 2026

This assessment originally made metadata-only recommendations. The user later approved
the more recent 2025 Q1 package, which completed for `$91.55`. See
`DATABENTO_2025Q1_DOWNLOAD_AND_PRIMARY_VERDICT.md`.

## Cost Model

The Apex-era `$4.98` cost was removed from the IBKR simulations and prospective
monitor before any prospective trades were observed.

Current modeled MNQ round-turn cost:

- IBKR commission, CME fee recovery, and regulatory recovery: approximately `$1.24`;
- one MNQ tick of slippage per side: `$1.00`;
- modeled total: `$2.24`.

IBKR overnight position fees remain separate and should be replaced with actual paper
account statements.

## Simulation Changes

One-position-at-a-time MNQ overnight results:

| Metric | Old $4.98 stress cost | Modeled $2.24 cost |
|---|---:|---:|
| Trades | 228 | 228 |
| Net PnL | $1,371.06 | $1,995.78 |
| Profit factor | 1.38 | 1.62 |
| Payoff ratio | 1.62 | 1.86 |
| Maximum drawdown | $803.20 | $557.18 |
| Worst day | -$214.34 | -$192.42 |

At `$10,000`, every historical one-position-at-a-time trade remains executable with a
`$1,000` entry reserve under the current margin snapshot. This is still searched,
non-independent history and does not validate profitability.

RTH-only MNQ results:

| Metric | Old $4.98 stress cost | Modeled $2.24 cost |
|---|---:|---:|
| Trades | 42 | 42 |
| Net PnL | $59.84 | $174.92 |
| Profit factor | 1.08 | 1.27 |
| Payoff ratio | 1.95 | 2.29 |
| Maximum drawdown | $291.46 | $217.48 |

At exactly `$5,000`, the historical path still becomes margin-ineligible after taking
only 15 of 42 RTH trades. `$5,200` takes every historical trade without a reserve, but
has only an `$80.12` minimum entry buffer. `$6,000` remains the more workable RTH-only
paper configuration.

## Databento Balance Limitation

The installed Databento API exposes metadata cost estimates but does not expose the
account's current free-credit balance. The portal must confirm the exact balance.

The already completed multi-futures daily/statistics/definition download cost
approximately `$4.52`. If the account began with `$125` free credit and no other
requests were billed, the implied remaining credit is approximately `$120.48`.

## Recommended Purchase Plan

Strict `$100` ceiling:

| Request | Cost | Size | Purpose |
|---|---:|---:|---|
| MNQ trades, Jan-May 2024 | $86.52 | 3.32 GB | Five untouched months for the selected delta formula and non-depth alternatives |
| MNQ+NQ OHLCV-1m, 2023-Mar 2026 | $13.02 | 0.20 GB | Price/volume-only alternatives |
| MNQ+NQ definitions | $0.02 | 0.01 GB | Contract and roll mapping |
| **Total** | **$99.56** | **3.53 GB** | |

With approximately `$120` available, extend the MNQ trades request through June 2024:

| Request | Cost | Size | Purpose |
|---|---:|---:|---|
| MNQ trades, Jan-Jun 2024 | $102.83 | 3.94 GB | Six untouched months for the selected delta formula and non-depth alternatives |
| MNQ+NQ OHLCV-1m, 2023-Mar 2026 | $13.02 | 0.20 GB | Price/volume-only alternatives |
| MNQ+NQ definitions | $0.02 | 0.01 GB | Contract and roll mapping |
| **Expanded total** | **$115.88** | **4.16 GB** | |

Do not spend the remaining credit on full depth. One month of MNQ `mbp-1` is estimated
at about `$101.93` and 60.8 GB by itself; one month of `mbp-10` is about `$182.34` and
391.6 GB. That would crowd out the independent strategy replication.

## What Each Dataset Can Validate

- `trades`: selected `vwap_delta_rejection` and other trade-delta candidates.
- `ohlcv-1m`: MACD, RSI, Donchian, Bollinger, VWAP-without-delta, and price/volume
  variants. It cannot validate aggressor delta.
- `bbo-1m`: broad spread/liquidity regime analysis, not exact fills.
- `bbo-1s`: better execution/slippage stress, still not full order-book replay.
- Full depth: depth-specific candidates only; currently poor value for the free credit.

The 2024 trades request should be analyzed only with the frozen primary first.
Testing all alternatives on it before recording the primary verdict would consume it
as another strategy-selection sample.
