package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func main() {
	var files multiFlag
	var frames multiIntFlag
	var riskBudgets multiFloatFlag
	var advisorDelays multiIntFlag
	var advisorMissRates multiFloatFlag
	flag.Var(&files, "file", "CSV export path. Repeat for multiple files.")
	flag.Var(&frames, "tf", "Timeframe in minutes. Repeat for multiple timeframes.")
	flag.Var(&riskBudgets, "risk-budget", "Dollar risk budget per trade. Repeat for multiple budgets.")
	flag.Var(&advisorDelays, "advisor-delay-bars", "Advisor/manual confirmation delay in bars. Repeat for multiple sensitivity rows.")
	flag.Var(&advisorMissRates, "advisor-miss-rate", "Advisor/manual missed signal rate. Use 0.10 for 10%; values >1 are treated as percent. Repeat for multiple sensitivity rows.")
	lookback := flag.Int("lookback", 20, "Swing lookback bars.")
	minWick := flag.Float64("min-wick", 0.35, "Minimum sweep wick share of total bar range.")
	minVolRatio := flag.Float64("min-vol-ratio", 1.2, "Minimum bar volume / trailing average volume.")
	minDepthImb := flag.Float64("min-depth-imbalance", 0.10, "Minimum top-depth imbalance for depth-confirmed variants.")
	macdFast := flag.Int("macd-fast", 12, "MACD fast EMA period.")
	macdSlow := flag.Int("macd-slow", 26, "MACD slow EMA period.")
	macdSignal := flag.Int("macd-signal", 9, "MACD signal EMA period.")
	depthLevels := flag.Int("depth-levels", 5, "Top market-depth levels to aggregate per bar.")
	exportDir := flag.String("export-dir", defaultExportDir(), "Directory used to auto-discover latest timestamped exports when no -file is supplied.")
	canonicalDir := flag.String("canonical-dir", "", "Canonical per-second partition directory. When set, raw export discovery and -file inputs are rejected.")
	exportSource := flag.String("export-source", "latest", "Auto-discovery source when no -file is supplied: latest, live, replayfill, or all.")
	instrumentFilter := flag.String("instrument", "", "Optional root instrument filter for auto-discovery, such as NQ or MNQ.")
	variantFilter := flag.String("variant", "", "Optional exact strategy variant to simulate. Leave empty to simulate all variants.")
	rr := flag.Float64("rr", 2.0, "Reward/risk target for trade simulation.")
	maxHold := flag.Int("max-hold", 20, "Maximum bars to hold after entry.")
	tickSize := flag.Float64("tick-size", 0.25, "Instrument tick size in points.")
	stopBufferTicks := flag.Float64("stop-buffer-ticks", 1.0, "Stop buffer beyond swept candle extreme, in ticks.")
	slippageTicks := flag.Float64("slippage-ticks", 0.0, "Adverse slippage on market entry and stop/timeout exit, in ticks. Ninja-close fill mode applies it to stop/timeout exits only.")
	fillMode := flag.String("fill-mode", "ninja_close", "Execution fill model: ninja_close approximates NinjaTrader OnBarClose market submission at signal close; next_bar_open uses the next bar open.")
	minRiskTicks := flag.Float64("min-risk-ticks", 0.0, "Skip simulated trades whose stop distance is below this many ticks. Use 0 to disable.")
	maxRiskTicks := flag.Float64("max-risk-ticks", 0.0, "Skip simulated trades whose stop distance is above this many ticks. Use 0 to disable.")
	maxEntryGapBars := flag.Int("max-entry-gap-bars", 2, "Skip entries when a bar timestamp gap exceeds this many expected bars. Use 0 to disable.")
	cleanBarsAfterGap := flag.Int("clean-bars-after-gap", 3, "Skip this many bars after a detected feed gap, matching Ninja-side reconnect warmup. Use 0 to disable warmup.")
	costPoints := flag.Float64("cost-points", 0.0, "Extra round-trip costs in points per contract, added to commission-derived costs.")
	commissionRT := flag.Float64("commission-round-turn", 3.98, "Round-turn commission/fees per contract in dollars.")
	pointValue := flag.Float64("point-value", 0.0, "Dollar value per full point. Use 0 to infer from instrument.")
	apexStartBalance := flag.Float64("apex-start-balance", 25000, "Apex account starting balance used for fixed-contract account simulation.")
	apexProfitTarget := flag.Float64("apex-profit-target", 1500, "Apex account profit target used for fixed-contract account simulation.")
	apexMaxDrawdown := flag.Float64("apex-max-drawdown", 1000, "Apex EOD max drawdown used for fixed-contract account simulation.")
	apexDailyLoss := flag.Float64("apex-daily-loss-limit", 500, "Apex daily loss limit used for fixed-contract account simulation.")
	apexMaxContracts := flag.Int("apex-max-contracts", 4, "Maximum fixed contract size to simulate.")
	advisorExpiryBars := flag.Int("advisor-expiry-bars", 2, "Maximum advisor/manual confirmation delay before a signal expires, in bars.")
	advisorMaxChaseR := flag.Float64("advisor-max-chase-r", 0.50, "Skip advisor/manual entries if delayed price has moved more than this R from the immediate next-bar entry. Use <=0 to disable.")
	staleFeedThresholdMinutes := flag.Float64("stale-feed-threshold-minutes", 3.0, "Warn when event timestamps advance this many minutes beyond the latest Last/Bid/Ask or bar_time.")
	barCacheDir := flag.String("bar-cache-dir", "", "Optional directory for per-export normalized 1m bar cache files. Reuses cached bars when file size, mtime, timezone, depth levels, and parser version match.")
	readWorkers := flag.Int("read-workers", 1, "Number of export files to parse/load in parallel. Use 1 for deterministic low-IO operation.")
	timezone := flag.String("timezone", "Europe/Kyiv", "Timezone used to parse NinjaTrader export timestamps.")
	sessionTimezone := flag.String("session-timezone", "America/New_York", "Timezone used for RTH/overnight and trading-day breakdowns.")
	outDir := flag.String("out", "reports", "Output report directory.")
	flag.Parse()
	if *canonicalDir != "" && len(files) != 0 {
		fatal(fmt.Errorf("-canonical-dir cannot be combined with raw -file inputs"))
	}
	if *staleFeedThresholdMinutes > 0 {
		staleFeedThreshold = time.Duration(*staleFeedThresholdMinutes * float64(time.Minute))
	}

	if loc, err := time.LoadLocation(*timezone); err == nil {
		ntLocation = loc
	} else {
		fmt.Fprintf(os.Stderr, "warning: could not load timezone %q, using local timezone: %v\n", *timezone, err)
	}
	if loc, err := time.LoadLocation(*sessionTimezone); err == nil {
		sessionLocation = loc
	} else {
		fmt.Fprintf(os.Stderr, "warning: could not load session timezone %q, using local timezone: %v\n", *sessionTimezone, err)
	}

	if *canonicalDir == "" && len(files) == 0 {
		files = discoverExports(*exportDir, *exportSource, *instrumentFilter)
		if len(files) == 0 {
			files = append(files,
				filepath.Join(*exportDir, "orderflow_tickses.csv"),
				filepath.Join(*exportDir, "orderflow_ticksnq.csv"))
		}
	}
	if len(frames) == 0 {
		frames = append(frames, 1, 5, 15)
	}
	if len(riskBudgets) == 0 {
		riskBudgets = append(riskBudgets, 10, 50, 100, 500, 1000)
	}
	if len(advisorDelays) == 0 {
		advisorDelays = append(advisorDelays, 0, 1, 2)
	}
	if len(advisorMissRates) == 0 {
		advisorMissRates = append(advisorMissRates, 0, 0.10, 0.25)
	}
	for i, rate := range advisorMissRates {
		if rate > 1 {
			advisorMissRates[i] = rate / 100.0
		}
		if advisorMissRates[i] < 0 {
			advisorMissRates[i] = 0
		}
		if advisorMissRates[i] > 1 {
			advisorMissRates[i] = 1
		}
	}

	if err := os.MkdirAll(*outDir, 0755); err != nil {
		fatal(err)
	}

	cfg := analysisConfig{
		Frames:            []int(frames),
		Lookback:          *lookback,
		MinWick:           *minWick,
		MinVolRatio:       *minVolRatio,
		MinDepthImb:       *minDepthImb,
		MACDFast:          *macdFast,
		MACDSlow:          *macdSlow,
		MACDSignal:        *macdSignal,
		RR:                *rr,
		MaxHold:           *maxHold,
		TickSize:          *tickSize,
		StopBufferTicks:   *stopBufferTicks,
		SlippageTicks:     *slippageTicks,
		FillMode:          normalizeFillMode(*fillMode),
		MinRiskTicks:      *minRiskTicks,
		MaxRiskTicks:      *maxRiskTicks,
		MaxEntryGapBars:   *maxEntryGapBars,
		CleanBarsAfterGap: *cleanBarsAfterGap,
		CostPoints:        *costPoints,
		CommissionRT:      *commissionRT,
		PointValue:        *pointValue,
		RiskBudgets:       []float64(riskBudgets),
		ApexStartBalance:  *apexStartBalance,
		ApexProfitTarget:  *apexProfitTarget,
		ApexMaxDrawdown:   *apexMaxDrawdown,
		ApexDailyLoss:     *apexDailyLoss,
		ApexMaxContracts:  *apexMaxContracts,
		AdvisorDelays:     []int(advisorDelays),
		AdvisorMissRates:  []float64(advisorMissRates),
		AdvisorExpiryBars: *advisorExpiryBars,
		AdvisorMaxChaseR:  *advisorMaxChaseR,
		OutDir:            *outDir,
		VariantFilter:     strings.TrimSpace(*variantFilter),
	}

	var datasets []dataset
	if *canonicalDir != "" {
		datasets = readCanonicalDatasets(*canonicalDir, *instrumentFilter, *depthLevels, *readWorkers)
		if len(datasets) == 0 {
			fatal(fmt.Errorf("no canonical partitions found in %s", *canonicalDir))
		}
	} else {
		datasets = readDatasets(files, *depthLevels, *barCacheDir, *readWorkers)
	}
	for _, ds := range datasets {
		analyzeDataset(ds, cfg)
	}
}

func analyzeDataset(ds dataset, cfg analysisConfig) {
	bars := ds.Bars
	st := ds.Stats
	pointValue := cfg.PointValue
	if pointValue <= 0 {
		pointValue = inferPointValue(st.Instrument)
	}
	commissionCostPoints := 0.0
	if cfg.CommissionRT > 0 && pointValue > 0 {
		commissionCostPoints = cfg.CommissionRT / pointValue
	}
	totalCostPoints := cfg.CostPoints + commissionCostPoints
	fmt.Printf("Analyzing %s: files=%d bars=%d rows=%d trades=%d quotes=%d depth=%d bad=%d\n",
		st.Instrument, len(ds.Files), len(bars), st.Rows, st.TradeRows, st.QuoteRows, st.DepthRows, st.BadRows)

	var lines []string
	lines = append(lines, fmt.Sprintf("# %s", st.Instrument))
	lines = append(lines, "")
	lines = append(lines, fmt.Sprintf("- Files: %d", len(ds.Files)))
	for _, file := range ds.Files {
		lines = append(lines, fmt.Sprintf("  - `%s`", file))
	}
	lines = append(lines, fmt.Sprintf("- Rows: %d", st.Rows))
	lines = append(lines, fmt.Sprintf("- Finalized 1m bars: %d", len(bars)))
	if st.TimeSource != "" {
		lines = append(lines, fmt.Sprintf("- Bar time source: %s", st.TimeSource))
	}
	lines = append(lines, fmt.Sprintf("- Trade rows: %d", st.TradeRows))
	lines = append(lines, fmt.Sprintf("- Quote rows: %d", st.QuoteRows))
	lines = append(lines, fmt.Sprintf("- Depth rows: %d", st.DepthRows))
	lines = append(lines, fmt.Sprintf("- Feed health rows: %d", st.HealthRows))
	lines = append(lines, fmt.Sprintf("- Connection status rows: %d", st.ConnectionStatusRows))
	lines = append(lines, fmt.Sprintf("- Bad rows skipped: %d", st.BadRows))
	lines = append(lines, fmt.Sprintf("- Incomplete live tail rows ignored: %d", st.IncompleteTailRows))
	lines = append(lines, fmt.Sprintf("- Bad timestamp rows unrepaired: %d", st.BadTimestampRows))
	lines = append(lines, fmt.Sprintf("- Repaired timestamps: %d", st.RepairedTimestampRows))
	if !st.BarStart.IsZero() {
		lines = append(lines, fmt.Sprintf("- Bar range: %s to %s", st.BarStart.Format(time.RFC3339), st.BarEnd.Format(time.RFC3339)))
	}
	if !st.EventStart.IsZero() {
		lines = append(lines, fmt.Sprintf("- Event timestamp range after repair: %s to %s", st.EventStart.Format(time.RFC3339), st.EventEnd.Format(time.RFC3339)))
	}
	if !st.LastTradeEvent.IsZero() || !st.LastBidEvent.IsZero() || !st.LastAskEvent.IsZero() || !st.LastDepthEvent.IsZero() {
		lines = append(lines, fmt.Sprintf("- Last data timestamps: Last=%s Bid=%s Ask=%s Depth=%s", formatTimeOrDash(st.LastTradeEvent), formatTimeOrDash(st.LastBidEvent), formatTimeOrDash(st.LastAskEvent), formatTimeOrDash(st.LastDepthEvent)))
	}
	if st.LastConnectionStatus != "" || st.LastPriceStatus != "" || st.LastHealthState != "" {
		lines = append(lines, fmt.Sprintf("- Last exporter health: connection=%s price=%s state=%s stale_seconds=%.1f max_stale_seconds=%.1f detail=%s", dash(st.LastConnectionStatus), dash(st.LastPriceStatus), dash(st.LastHealthState), st.LastHealthStaleSeconds, st.MaxHealthStaleSeconds, dash(st.LastHealthDetail)))
	}
	if len(st.Warnings) > 0 {
		lines = append(lines, "", "## Data Quality Warnings", "")
		for _, warning := range st.Warnings {
			lines = append(lines, "- "+warning)
		}
	}
	lines = append(lines, "")
	lines = append(lines, "## Trade Simulation")
	lines = append(lines, "")
	lines = append(lines, fmt.Sprintf("%s Stop is beyond the signal candle extreme by %.2f ticks unless the signal uses an ATR stop. Target is %.2fR. Max hold is %d bars. Slippage setting is %.2f ticks. Risk filters are min %.1f ticks and max %.1f ticks. Feed-gap guard skips gaps over %d bars and the next %d warmup bars. Costs subtract %.4f points per contract per trade.", fillModeDescription(cfg.FillMode), cfg.StopBufferTicks, cfg.RR, cfg.MaxHold, cfg.SlippageTicks, cfg.MinRiskTicks, cfg.MaxRiskTicks, cfg.MaxEntryGapBars, cfg.CleanBarsAfterGap, totalCostPoints))
	if pointValue > 0 {
		lines = append(lines, fmt.Sprintf("Point value is $%.2f per point. Commission is $%.2f round-turn per contract, equal to %.4f points. Extra cost override is %.4f points.", pointValue, cfg.CommissionRT, commissionCostPoints, cfg.CostPoints))
	} else {
		lines = append(lines, "Point value could not be inferred, so dollar risk-budget assessment is unavailable for this instrument.")
	}
	lines = append(lines, "Depth variants use top-book depth snapshots when present, otherwise they fall back to best bid/ask quote-size imbalance from market-data quote rows.")
	lines = append(lines, fmt.Sprintf("MACD variants use %d/%d/%d EMA settings on each resampled close.", cfg.MACDFast, cfg.MACDSlow, cfg.MACDSignal))
	lines = append(lines, "")
	lines = append(lines, "| TF | Variant | Trades | Win rate | Avg R | Total R | PF | Max DD R | Target | Stop | Timeout | Avg risk pts | Avg MFE R | Avg MAE R |")
	lines = append(lines, "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

	var allTrades []trade
	var advisorRows []advisorRow
	addVariant := func(tf int, series []bar, name string, sigs []signal) {
		if cfg.VariantFilter != "" && name != cfg.VariantFilter {
			return
		}
		trades := simulateTrades(st.Instrument, series, sigs, name, tf, cfg, totalCostPoints)
		allTrades = append(allTrades, trades...)
		advisorRows = append(advisorRows, buildAdvisorRows(st.Instrument, series, sigs, name, tf, cfg, totalCostPoints)...)
		s := summarizeTrades(trades)
		lines = append(lines, fmt.Sprintf("| %dm | %s | %d | %.1f%% | %.3f | %.3f | %s | %.3f | %d | %d | %d | %.4f | %.3f | %.3f |",
			tf, name, s.Trades, summaryWinRate(s), s.AvgR, s.TotalR, formatPF(s.ProfitFactor), s.MaxDrawdownR, s.Targets, s.Stops, s.Timeouts, s.AvgRiskPoints, s.AvgMFER, s.AvgMAER))
	}
	for _, tf := range cfg.Frames {
		series := resample(bars, tf)
		if len(series) < cfg.Lookback+25 {
			lines = append(lines, fmt.Sprintf("| %dm | insufficient bars (%d) | | | | | | | | | | | | |", tf, len(series)))
			continue
		}
		variants := []struct {
			name         string
			requireVol   bool
			requireDelta bool
			requireDepth bool
		}{
			{"raw_sfp", false, false, false},
			{"volume_sfp", true, false, false},
			{"delta_sfp", false, true, false},
			{"volume_delta_sfp", true, true, false},
			{"depth_sfp", false, false, true},
			{"volume_delta_depth_sfp", true, true, true},
		}
		for _, v := range variants {
			sigs := detectSignals(series, cfg.Lookback, cfg.MinWick, cfg.MinVolRatio, cfg.MinDepthImb, v.requireVol, v.requireDelta, v.requireDepth)
			addVariant(tf, series, v.name, sigs)
		}
		macdVariants := []struct {
			name             string
			requireZeroTrend bool
		}{
			{"macd_cross", false},
			{"macd_zero_trend", true},
		}
		for _, v := range macdVariants {
			sigs := detectMACDSignals(series, cfg.MACDFast, cfg.MACDSlow, cfg.MACDSignal, cfg.Lookback, v.requireZeroTrend)
			addVariant(tf, series, v.name, sigs)
		}
		researchVariants := []struct {
			name string
			sigs []signal
		}{
			{"donchian_breakout", detectDonchianBreakoutSignals(series, cfg.Lookback, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false, false)},
			{"donchian_volume_delta", detectDonchianBreakoutSignals(series, cfg.Lookback, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, false)},
			{"donchian_depth_delta", detectDonchianBreakoutSignals(series, cfg.Lookback, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, true)},
			{"bollinger_breakout", detectBollingerBreakoutSignals(series, 20, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false, false)},
			{"bollinger_volume_delta", detectBollingerBreakoutSignals(series, 20, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, false)},
			{"rsi_reversion", detectRSIReversionSignals(series, 14, cfg.Lookback)},
			{"depth_delta_momentum", detectDepthDeltaMomentumSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb)},
			{"vwap_reclaim", detectVWAPReclaimSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false)},
			{"vwap_delta_reclaim", detectVWAPReclaimSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"vwap_rejection", detectVWAPRejectionSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false)},
			{"vwap_delta_rejection", detectVWAPRejectionSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"orb15_breakout", detectOpeningRangeSignals(series, 15, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true, true)},
			{"orb15_retest", detectOpeningRangeSignals(series, 15, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, true)},
			{"orb30_breakout", detectOpeningRangeSignals(series, 30, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true, true)},
			{"orb30_retest", detectOpeningRangeSignals(series, 30, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, true)},
			{"value_rejection", detectPriorValueAreaSignals(series, cfg.TickSize, cfg.Lookback, cfg.MinVolRatio, false, false)},
			{"value_breakout", detectPriorValueAreaSignals(series, cfg.TickSize, cfg.Lookback, cfg.MinVolRatio, true, true)},
			{"opening_drive_pullback", detectOpeningDrivePullbackSignals(series, 30, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)},
			{"opening_drive_failure", detectOpeningDriveFailureSignals(series, 30, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)},
			{"ib_acceptance", detectInitialBalanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"ib_rejection", detectInitialBalanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"ib_strict_acceptance", detectInitialBalanceStrictAcceptanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)},
			{"vwap_slope_pullback", detectVWAPSlopeSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"vwap_flat_reversion", detectVWAPSlopeSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"value_reclaim", detectPriorValueReclaimSignals(series, cfg.TickSize, cfg.Lookback, cfg.MinVolRatio, true)},
			{"vwap_absorption_reversal", detectVWAPAbsorptionReversalSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)},
			{"prior_rth_high_reclaim", detectSessionLevelSignals(series, "prior_rth_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"prior_rth_low_reclaim", detectSessionLevelSignals(series, "prior_rth_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"prior_rth_close_reclaim", detectSessionLevelSignals(series, "prior_rth_close", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"prior_rth_vwap_reclaim", detectSessionLevelSignals(series, "prior_rth_vwap", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"overnight_high_reclaim", detectSessionLevelSignals(series, "overnight_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"overnight_low_reclaim", detectSessionLevelSignals(series, "overnight_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)},
			{"prior_rth_high_rejection", detectSessionLevelSignals(series, "prior_rth_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"prior_rth_low_rejection", detectSessionLevelSignals(series, "prior_rth_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"overnight_high_rejection", detectSessionLevelSignals(series, "overnight_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
			{"overnight_low_rejection", detectSessionLevelSignals(series, "overnight_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)},
		}
		for _, v := range researchVariants {
			addVariant(tf, series, v.name, v.sigs)
		}
		if tf == 1 {
			macdZero := detectMACDSignals(series, cfg.MACDFast, cfg.MACDSlow, cfg.MACDSignal, cfg.Lookback, true)
			addVariant(tf, series, "mtf60_macd0_1m_macd0", filterSignalsByRegime(series, macdZero, bars, 60, "macd_zero_trend"))
			bollingerBreakout := detectBollingerBreakoutSignals(series, 20, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false, false)
			bollingerVolumeDelta := detectBollingerBreakoutSignals(series, 20, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, false)
			donchianBreakout := detectDonchianBreakoutSignals(series, cfg.Lookback, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false, false)
			rsiReversion := detectRSIReversionSignals(series, 14, cfg.Lookback)
			or30DrivePullback := detectOpeningDrivePullbackSignals(series, 30, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)
			or30DriveFailure := detectOpeningDriveFailureSignals(series, 30, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)
			ibRejection := detectInitialBalanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			ibStrictAcceptance := detectInitialBalanceStrictAcceptanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)
			priorRTHHighReclaim := detectSessionLevelSignals(series, "prior_rth_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			priorRTHLowReclaim := detectSessionLevelSignals(series, "prior_rth_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			overnightHighReclaim := detectSessionLevelSignals(series, "overnight_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			overnightLowReclaim := detectSessionLevelSignals(series, "overnight_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			addVariant(tf, series, "rth_open_1m_bollinger_breakout", filterSignalsBySessionSegment(series, bollingerBreakout, "rth_open_09_30_11_00"))
			addVariant(tf, series, "rth_open_1m_bollinger_volume_delta", filterSignalsBySessionSegment(series, bollingerVolumeDelta, "rth_open_09_30_11_00"))
			addVariant(tf, series, "rth_open_1m_donchian_breakout", filterSignalsBySessionSegment(series, donchianBreakout, "rth_open_09_30_11_00"))
			addVariant(tf, series, "rth_open_1m_or30_drive_pullback", filterSignalsBySessionSegment(series, or30DrivePullback, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_or30_drive_failure", filterSignalsBySessionSegment(series, or30DriveFailure, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_ib_rejection", filterSignalsBySessionSegment(series, ibRejection, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_ib_strict_acceptance", filterSignalsBySessionSegment(series, ibStrictAcceptance, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_prior_rth_high_reclaim", filterSignalsBySessionSegment(series, priorRTHHighReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_prior_rth_low_reclaim", filterSignalsBySessionSegment(series, priorRTHLowReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_overnight_high_reclaim", filterSignalsBySessionSegment(series, overnightHighReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_1m_overnight_low_reclaim", filterSignalsBySessionSegment(series, overnightLowReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_lunch_1m_donchian_breakout", filterSignalsBySessionSegment(series, donchianBreakout, "rth_lunch_11_30_13_30"))
			addVariant(tf, series, "rth_lunch_1m_rsi_reversion", filterSignalsBySessionSegment(series, rsiReversion, "rth_lunch_11_30_13_30"))
		}
		if tf == 5 {
			rsi := detectRSIReversionSignals(series, 14, cfg.Lookback)
			vwapReject := detectVWAPRejectionSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false)
			orb15Retest := detectOpeningRangeSignals(series, 15, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true, true)
			valueReject := detectPriorValueAreaSignals(series, cfg.TickSize, cfg.Lookback, cfg.MinVolRatio, false, false)
			bollingerBreakout := detectBollingerBreakoutSignals(series, 20, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false, false)
			vwapRejection := detectVWAPRejectionSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, false)
			ibAcceptance := detectInitialBalanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)
			ibRejection := detectInitialBalanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			ibStrictAcceptance := detectInitialBalanceStrictAcceptanceSignals(series, 60, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true)
			vwapSlopePullback := detectVWAPSlopeSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, true, true)
			vwapFlatReversion := detectVWAPSlopeSignals(series, cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			valueReclaim := detectPriorValueReclaimSignals(series, cfg.TickSize, cfg.Lookback, cfg.MinVolRatio, true)
			priorRTHVWAPReclaim := detectSessionLevelSignals(series, "prior_rth_vwap", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			overnightHighReclaim := detectSessionLevelSignals(series, "overnight_high", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			overnightLowReclaim := detectSessionLevelSignals(series, "overnight_low", cfg.Lookback, cfg.MinVolRatio, cfg.MinDepthImb, false, true)
			addVariant(tf, series, "mtf60_adx_5m_rsi", filterSignalsByRegime(series, rsi, bars, 60, "adx_dmi"))
			addVariant(tf, series, "mtf60_macdhist_5m_rsi", filterSignalsByRegime(series, rsi, bars, 60, "macd_hist"))
			addVariant(tf, series, "mtf60_macd0_5m_vwap_reject", filterSignalsByRegime(series, vwapReject, bars, 60, "macd_zero_trend"))
			addVariant(tf, series, "mtf60_adx_5m_vwap_reject", filterSignalsByRegime(series, vwapReject, bars, 60, "adx_dmi"))
			addVariant(tf, series, "mtf60_macd0_5m_orb15_retest", filterSignalsByRegime(series, orb15Retest, bars, 60, "macd_zero_trend"))
			addVariant(tf, series, "mtf60_macd0_5m_value_reject", filterSignalsByRegime(series, valueReject, bars, 60, "macd_zero_trend"))
			addVariant(tf, series, "rth_close_5m_bollinger_breakout", filterSignalsBySessionSegment(series, bollingerBreakout, "rth_close_15_00_16_00"))
			addVariant(tf, series, "rth_lunch_5m_vwap_rejection", filterSignalsBySessionSegment(series, vwapRejection, "rth_lunch_11_30_13_30"))
			addVariant(tf, series, "rth_open_5m_ib_acceptance", filterSignalsBySessionSegment(series, ibAcceptance, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_5m_ib_rejection", filterSignalsBySessionSegment(series, ibRejection, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_5m_ib_strict_acceptance", filterSignalsBySessionSegment(series, ibStrictAcceptance, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_5m_vwap_slope_pullback", filterSignalsBySessionSegment(series, vwapSlopePullback, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_lunch_5m_vwap_flat_reversion", filterSignalsBySessionSegment(series, vwapFlatReversion, "rth_lunch_11_30_13_30"))
			addVariant(tf, series, "rth_open_5m_value_reclaim", filterSignalsBySessionSegment(series, valueReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_5m_prior_rth_vwap_reclaim", filterSignalsBySessionSegment(series, priorRTHVWAPReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_5m_overnight_high_reclaim", filterSignalsBySessionSegment(series, overnightHighReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
			addVariant(tf, series, "rth_open_5m_overnight_low_reclaim", filterSignalsBySessionSegment(series, overnightLowReclaim, "rth_open_09_30_11_00", "rth_mid_11_00_11_30"))
		}
	}
	lines = appendAdvisorSensitivity(lines, advisorRows, cfg)
	regimeRows := buildRegimeFilterRows(allTrades, bars)
	regimeTradeRows := buildRegimeTradeRows(allTrades, bars)
	dayRegimes := buildDayRegimes(bars, 5)
	dayRegimeRows := buildDayRegimeStrategyRows(allTrades, dayRegimes, pointValue)
	daySelectorRows := buildDayRegimeSelectorRows(allTrades, dayRegimes, pointValue)
	lines = appendRegimeFilterBreakdown(lines, regimeRows)
	lines = appendDayRegimeBreakdown(lines, dayRegimes, dayRegimeRows, daySelectorRows)
	lines = appendRiskBudgetAssessment(lines, allTrades, cfg.RiskBudgets, pointValue, cfg.SlippageTicks*cfg.TickSize, totalCostPoints)
	lines = appendApexAccountSimulation(lines, allTrades, pointValue, totalCostPoints, cfg)
	lines = appendBreakdown(lines, "Session Rollup", fmt.Sprintf("Grouped by entry time in `%s`.", sessionLocation.String()), allTrades, func(tr trade) string {
		return sessionRollup(tr.EntryTime)
	})
	lines = appendBreakdown(lines, "RTH Segment Breakdown", fmt.Sprintf("Grouped by entry time in `%s`; segments are non-overlapping.", sessionLocation.String()), allTrades, func(tr trade) string {
		return sessionSegment(tr.EntryTime)
	})
	lines = appendBreakdown(lines, "Trading Day Breakdown", fmt.Sprintf("Grouped by futures trading day in `%s`, rolling the day at 18:00.", sessionLocation.String()), allTrades, func(tr trade) string {
		return tradingDay(tr.EntryTime)
	})

	name := safeName(st.Instrument)
	if name == "" {
		name = ds.Key
	}
	reportPath := filepath.Join(cfg.OutDir, name+"_analysis.md")
	if err := os.WriteFile(reportPath, []byte(strings.Join(lines, "\n")+"\n"), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "error writing report: %v\n", err)
		return
	}
	tradesPath := filepath.Join(cfg.OutDir, name+"_trades.csv")
	if err := writeTradesCSV(tradesPath, allTrades); err != nil {
		fmt.Fprintf(os.Stderr, "error writing trades: %v\n", err)
		return
	}
	advisorPath := filepath.Join(cfg.OutDir, name+"_advisor_sensitivity.csv")
	if err := writeAdvisorCSV(advisorPath, advisorRows); err != nil {
		fmt.Fprintf(os.Stderr, "error writing advisor sensitivity: %v\n", err)
		return
	}
	regimePath := filepath.Join(cfg.OutDir, name+"_regime_filters.csv")
	if err := writeRegimeFilterCSV(regimePath, regimeRows); err != nil {
		fmt.Fprintf(os.Stderr, "error writing regime filter rows: %v\n", err)
		return
	}
	regimeTradesPath := filepath.Join(cfg.OutDir, name+"_regime_trades.csv")
	if err := writeRegimeTradeCSV(regimeTradesPath, regimeTradeRows); err != nil {
		fmt.Fprintf(os.Stderr, "error writing regime trade rows: %v\n", err)
		return
	}
	dayRegimePath := filepath.Join(cfg.OutDir, name+"_day_regimes.csv")
	if err := writeDayRegimeCSV(dayRegimePath, dayRegimes); err != nil {
		fmt.Fprintf(os.Stderr, "error writing day regime rows: %v\n", err)
		return
	}
	dayRegimeStrategyPath := filepath.Join(cfg.OutDir, name+"_day_regime_strategies.csv")
	if err := writeDayRegimeStrategyCSV(dayRegimeStrategyPath, dayRegimeRows); err != nil {
		fmt.Fprintf(os.Stderr, "error writing day regime strategy rows: %v\n", err)
		return
	}
	daySelectorPath := filepath.Join(cfg.OutDir, name+"_day_regime_selector.csv")
	if err := writeDayRegimeSelectorCSV(daySelectorPath, daySelectorRows); err != nil {
		fmt.Fprintf(os.Stderr, "error writing day regime selector rows: %v\n", err)
		return
	}
	fmt.Printf("  wrote %s\n", reportPath)
	fmt.Printf("  wrote %s\n", tradesPath)
	fmt.Printf("  wrote %s\n", advisorPath)
	fmt.Printf("  wrote %s\n", regimePath)
	fmt.Printf("  wrote %s\n", regimeTradesPath)
	fmt.Printf("  wrote %s\n", dayRegimePath)
	fmt.Printf("  wrote %s\n", dayRegimeStrategyPath)
	fmt.Printf("  wrote %s\n", daySelectorPath)
}
