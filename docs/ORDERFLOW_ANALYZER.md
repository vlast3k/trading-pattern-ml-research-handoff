# Trading Analyzer

Streaming Go analyzer for NinjaTrader `OrderFlowCsvExporter` CSV files.

It reads multi-GB exports without loading raw rows into memory, collapses repeated
market-data snapshots into finalized bars, builds bid/ask delta from `Last` rows,
uses throttled top-book depth snapshots when available,
repairs bad `1970-01-01` event timestamps from the row `bar_time`, resamples to
1m/5m/15m, and simulates SFP / stop-sweep reversal, MACD crossover,
breakout, reversion, and order-flow momentum trades.

If a Ninja chart was not a 1-minute chart and its `bar_time` column is too
coarse, the analyzer automatically falls back to rebuilding 1-minute OHLCV bars
from event timestamps and `Last` trade prices. Reports show this as
`Bar time source: event_timestamp_1m`; normal 1-minute chart exports show
`Bar time source: bar_time`.

## WSL Setup

Check WSL from PowerShell:

```powershell
wsl --list --verbose
wsl --status
```

## Run In WSL

From Ubuntu:

```bash
cd /mnt/c/Users/I032581/vladi/test
sudo apt update
sudo apt install -y golang-go
go run ./src/orderflow_analyzer \
  -tf 1 -tf 5 -tf 15 \
  -timezone Europe/Kyiv \
  -session-timezone America/New_York \
  -rr 2 \
  -max-hold 20 \
  -macd-fast 12 \
  -macd-slow 26 \
  -macd-signal 9 \
  -advisor-delay-bars 0 \
  -advisor-delay-bars 1 \
  -advisor-delay-bars 2 \
  -advisor-miss-rate 0 \
  -advisor-miss-rate 0.10 \
  -advisor-miss-rate 0.25 \
  -advisor-expiry-bars 2 \
  -advisor-max-chase-r 0.50 \
  -slippage-ticks 1 \
  -commission-round-turn 3.98 \
  -risk-budget 10 \
  -risk-budget 50 \
  -risk-budget 100 \
  -risk-budget 500 \
  -risk-budget 1000 \
  -apex-start-balance 25000 \
  -apex-profit-target 1500 \
  -apex-max-drawdown 1000 \
  -apex-daily-loss-limit 500 \
  -apex-max-contracts 4
```

Reports are written to:

```text
reports/
```

For the current full ES/NQ session, WSL can run the checked-in helper:

```bash
bash scripts/run_full_session_analysis.sh
```

You can also pass explicit rotated-session roots:

```bash
bash scripts/run_full_session_analysis.sh \
  orderflow_ES_06-26_20260514_173739_247_503aa5a8 \
  orderflow_NQ_06-26_20260514_173739_266_3f48f63c
```

When no `-file` is supplied, the analyzer looks in the NinjaTrader export folder
and automatically picks all chunks from the newest timestamped rotated recording
set per root symbol, such as ES and NQ:

```text
orderflow_ES_06-26_20260514_071234_123_part001.csv
orderflow_ES_06-26_20260514_071234_123_part002.csv
```

If no rotated timestamped files exist yet, it falls back to the old fixed ES/NQ
filenames.

Each instrument gets:

- `*_analysis.md` summary with repaired timestamp counts, bar range, trade simulation stats, RTH/overnight breakdowns, RTH segment breakdowns, and futures trading-day breakdowns.
- `*_trades.csv` per-signal trade details including entry, stop, target, R, MFE/MAE, delta, top-depth or quote-size imbalance, session bucket, RTH segment, and trading day.
- `*_advisor_sensitivity.csv` per-strategy sensitivity rows for manual/advisor execution delays and missed signals.

The analyzer infers futures point value for ES/MES/NQ/MNQ and can convert
round-turn commission into points. The risk-budget table treats values such as
`-risk-budget 100` as maximum planned stop-loss dollars per trade, rounds down
to whole contracts, and skips trades whose stop risk cannot fit even one
contract inside that budget.

It also emits an Apex 25K fixed-contract simulation. That table runs each
strategy with 1..4 contracts, applies PnL and commissions, checks intratrade
adverse excursion against the $1,000 EOD drawdown threshold, pauses new trades
after a $500 daily loss limit, and marks whether the $1,500 profit target was
reached.

MACD variants use standard signal-line crosses by default: `macd_cross` records
all bullish/bearish crosses, while `macd_zero_trend` only keeps bullish crosses
above zero and bearish crosses below zero.

Additional research variants are included for NQ/MNQ validation:

- `donchian_breakout`: close outside the previous lookback high/low.
- `donchian_volume_delta`: Donchian breakout with volume and delta confirmation.
- `donchian_depth_delta`: Donchian breakout with volume, delta, and top-depth confirmation.
- `bollinger_breakout`: close outside a 20-period, 2-sigma band.
- `bollinger_volume_delta`: Bollinger breakout with volume and delta confirmation.
- `rsi_reversion`: RSI 14 cross back from oversold/overbought.
- `depth_delta_momentum`: candle direction, delta, volume, and top-depth imbalance align.
- `vwap_reclaim` / `vwap_delta_reclaim`: lower-timeframe close reclaiming session VWAP, optionally with volume and delta confirmation.
- `vwap_rejection` / `vwap_delta_rejection`: lower-timeframe pullback into session VWAP that rejects back in the prior side's direction.
- `orb15_breakout`, `orb15_retest`, `orb30_breakout`, `orb30_retest`: RTH opening-range breakout and retest entries.
- `value_rejection` / `value_breakout`: prior-session bar-based value-area rejection or acceptance outside value.
- `mtf60_*`: materialized 60-minute regime plus lower-timeframe entry combinations, so daily reruns can compare the exact same higher/lower-timeframe ideas without post-processing.

Advisor sensitivity models an honest human-supervised workflow. The strategy
produces a signal, the human may miss some signals, and accepted signals enter
after a configured delay. Delay is measured in bars for the analyzed timeframe:
`-advisor-delay-bars 1` means about 1 minute on 1m, 5 minutes on 5m, and 15
minutes on 15m. `-advisor-miss-rate` accepts either fractions such as `0.10` or
percent values such as `10`. `-advisor-max-chase-r` skips delayed entries that
have already moved too far in the trade direction.

Use this section to find the point where manual execution stops making sense.
If a candidate only works at `delay=0` and `miss=0%`, treat it as unsuitable for
manual advisory trading.

The NinjaTrader exporter writes rotated files with `Max file size MB` defaulting
to `50`, so each recording session may produce several `partNNN` CSV chunks.
It keeps raw trade/quote rows, but market depth is written as periodic top-book
snapshots. The default `Depth snapshot milliseconds` value is `250`, with total
bid depth, total ask depth, and depth imbalance appended on each snapshot row.
The default `Max depth position` is `9`, meaning levels `0..9` are recorded, and
each row also includes the current best-bid/best-ask `spread` and `mid_price`.

## Compress Old Exports

The analyzer reads both plain `*.csv` and gzipped `*.csv.gz` export chunks. To
reduce disk use after NinjaTrader has rotated away from older parts:

```bash
scripts/gzip_ninjatrader_exports.sh --dry-run
scripts/gzip_ninjatrader_exports.sh --min-age-minutes 60
```

The compressor only targets `orderflow_*.csv`, skips recent files, skips files
that already have a `.gz`, and checks that file size is stable before replacing
the CSV with a timestamp-preserving gzip file.
