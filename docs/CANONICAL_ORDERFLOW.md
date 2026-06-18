# Canonical Order-Flow Dataset

The canonical research dataset is a compressed, per-second view of all usable
live and downloaded/replay exports. It is not a one-minute bar dataset.

For every instrument and second, it independently selects the strongest
available source for:

- trades;
- bid/ask quotes; and
- full depth snapshots at positions `0..9`.

This permits a second to use live trades and replay depth, or replay for all
three components when no live recording exists. Equal-coverage ties prefer
live data. Separate overlapping recordings are never summed together.

Each compressed daily file includes:

- trade OHLC, volume, count, and buy/sell/unknown volume;
- bid/ask update counts, last prices/sizes, and spread range;
- last ten-level bid and ask book snapshot;
- depth snapshot count, total bid/ask depth, and imbalance range/average; and
- separate provenance for trade, quote, and depth components.

Build after exports stop changing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Build-CanonicalOrderFlowSeconds.ps1
```

Outputs are partitioned under `data\canonical_orderflow_1s` by instrument and
event date. Incremental per-input shards are stored under
`reports\runtime\canonical_orderflow_shards`.

Run the same build command whenever more replay days or live exports are
available. The builder tracks each source file:

- unchanged exports are skipped;
- new exports create only their affected instrument/day partitions;
- changed exports replace their old shards and refresh their affected days;
- existing unrelated canonical days are not rebuilt.

Run strategy analysis only from canonical partitions:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Run-CanonicalOrderFlowAnalysis.ps1
```

The analyzer's `-canonical-dir` mode is exclusive: it rejects raw `-file`
inputs and does not discover raw exports. It builds deterministic one-minute
bars from the canonical seconds, then resamples those bars for the existing
1m/5m/15m strategy families.

The raw compressed exports remain the lossless archive. The canonical seconds
preserve second-level book evolution and features suitable for broad strategy
research, but do not preserve the exact ordering of multiple events within the
same second.

Timestamp interpretation is source-specific. NinjaTrader live exports use the
Windows/NinjaTrader local timezone (`Europe/Kyiv` on this machine), while
Playback/Market Replay exports use US Eastern time (`America/New_York`). The
build wrapper passes both explicitly; changing either timezone invalidates the
affected shard identities.

Canonical datasets built before format version 3 interpreted replay clocks as
Kyiv local time and must not be used for strategy conclusions. Rebuild the
canonical dataset and rerun analysis after upgrading the builder.
