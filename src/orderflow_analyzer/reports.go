package main

import (
	"fmt"
	"math"
	"sort"
	"time"
)

func appendDayRegimeBreakdown(lines []string, regimes []dayRegime, strategyRows []dayRegimeStrategyRow, selectorRows []dayRegimeSelectorRow) []string {
	lines = append(lines, "", "## Day-Regime Selector", "")
	lines = append(lines, "This classifier uses only RTH information that is knowable by 10:00 ET: overnight gap, first 5/15/30 minute range, first 30 minute return, and first 30 minute volume z-score versus recent prior recorded days. Strategy rows below only count RTH trades entered at or after 10:00 ET, so the selector does not use first-30-minute information for earlier trades.")
	lines = append(lines, "")
	if len(regimes) == 0 {
		lines = append(lines, "No day-regime rows.")
		return lines
	}

	lines = append(lines, "### Daily Regime Features", "")
	lines = append(lines, "| Day | Regime | Complete | Gap | OR5 | OR15 | OR30 | OR30 Bars | OR30 Ret | OR30 Vol Z | OR30 Range Z | Labels |")
	lines = append(lines, "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
	for _, dr := range regimes {
		lines = append(lines, fmt.Sprintf("| %s | %s | %t | %.2f | %.2f | %.2f | %.2f | %d | %.2f | %.2f | %.2f | %s / %s / %s / %s |",
			dr.Day,
			dr.RegimeLabel,
			dr.Complete,
			dr.GapPoints,
			dr.OR5Range,
			dr.OR15Range,
			dr.OR30Range,
			dr.OR30Bars,
			dr.OR30Return,
			dr.OR30VolumeZ,
			dr.OR30RangeZ,
			dr.GapLabel,
			dr.BiasLabel,
			dr.RangeLabel,
			dr.VolumeLabel))
	}

	top := append([]dayRegimeStrategyRow(nil), strategyRows...)
	sort.Slice(top, func(i, j int) bool {
		a, b := top[i], top[j]
		if a.Summary.Summary.TotalR != b.Summary.Summary.TotalR {
			return a.Summary.Summary.TotalR > b.Summary.Summary.TotalR
		}
		return a.Summary.Dollars > b.Summary.Dollars
	})

	lines = append(lines, "", "### Best In-Sample Strategy By Day Regime", "")
	lines = append(lines, "| Regime | TF | Variant | Trades | Win | Total R | PnL | PF | Max DD | Days |")
	lines = append(lines, "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
	added := 0
	for _, row := range top {
		if row.Summary.Summary.Trades < 3 || row.Summary.Summary.TotalR <= 0 {
			continue
		}
		lines = append(lines, dayRegimeStrategyMarkdownRow(row))
		added++
		if added >= 25 {
			break
		}
	}
	if added == 0 {
		lines = append(lines, "| - | - | no positive rows with at least 3 trades | | | | | | | |")
	}

	lines = append(lines, "", "### Walk-Forward Strategy Selector", "")
	lines = append(lines, "For each day, the selector picks one candidate using only prior days. It first tries prior days with the same regime and at least 3 trades; if unavailable, it falls back to all prior days with at least 5 trades. This is still a small-sample research check, not a production allocation rule.")
	lines = append(lines, "")
	lines = append(lines, "| Mode | Day | Regime | Source | Selected | Prior trades | Prior R | Day trades | Day R | Day PnL |")
	lines = append(lines, "|---|---|---|---|---|---:|---:|---:|---:|---:|")
	totals := make(map[string]dollarSummary)
	var totalModes []string
	for _, row := range selectorRows {
		lines = append(lines, fmt.Sprintf("| %s | %s | %s | %s | %dm %s | %d | %.3f | %d | %.3f | %s |",
			row.Mode,
			row.Day,
			row.Regime,
			row.Source,
			row.Timeframe,
			row.Variant,
			row.PriorTrades,
			row.PriorTotalR,
			row.Summary.Summary.Trades,
			row.Summary.Summary.TotalR,
			formatMoney(row.Summary.Dollars)))
		if _, ok := totals[row.Mode]; !ok {
			totalModes = append(totalModes, row.Mode)
		}
		totals[row.Mode] = addDollarSummary(totals[row.Mode], row.Summary)
	}
	if len(selectorRows) == 0 {
		lines = append(lines, "| - | - | - | no prior candidate met minimum evidence | | | | | | |")
	} else {
		sort.Strings(totalModes)
		for _, mode := range totalModes {
			total := totals[mode]
			lines = append(lines, fmt.Sprintf("| %s total | - | - | - | - | - | - | %d | %.3f | %s |",
				mode,
				total.Summary.Trades,
				total.Summary.TotalR,
				formatMoney(total.Dollars)))
		}
	}

	lines = append(lines, "")
	lines = append(lines, "Full day-regime details are written to `*_day_regimes.csv`, `*_day_regime_strategies.csv`, and `*_day_regime_selector.csv`.")
	return lines
}

func dayRegimeStrategyMarkdownRow(row dayRegimeStrategyRow) string {
	s := row.Summary.Summary
	return fmt.Sprintf("| %s | %dm | %s | %d | %.1f%% | %.3f | %s | %s | %s | %d/%d/%d |",
		row.Key.Regime,
		row.Key.Timeframe,
		row.Key.Variant,
		s.Trades,
		summaryWinRate(s),
		s.TotalR,
		formatMoney(row.Summary.Dollars),
		formatPF(s.ProfitFactor),
		formatMoney(row.Summary.MaxDrawdown),
		row.Summary.PositiveDays,
		row.Summary.NegativeDays,
		row.Summary.Days)
}

func addDollarSummary(a, b dollarSummary) dollarSummary {
	a.Summary.Trades += b.Summary.Trades
	a.Summary.Wins += b.Summary.Wins
	a.Summary.Losses += b.Summary.Losses
	a.Summary.Targets += b.Summary.Targets
	a.Summary.Stops += b.Summary.Stops
	a.Summary.Timeouts += b.Summary.Timeouts
	a.Summary.TotalR += b.Summary.TotalR
	a.Dollars += b.Dollars
	if b.MaxDrawdown > a.MaxDrawdown {
		a.MaxDrawdown = b.MaxDrawdown
	}
	a.Days += b.Days
	a.PositiveDays += b.PositiveDays
	a.NegativeDays += b.NegativeDays
	if a.Summary.Trades > 0 {
		a.Summary.AvgR = a.Summary.TotalR / float64(a.Summary.Trades)
	}
	return a
}

func appendRegimeFilterBreakdown(lines []string, rows []regimeFilterRow) []string {
	lines = append(lines, "", "## Multi-Timeframe Regime Filters", "")
	if len(rows) == 0 {
		lines = append(lines, "No regime filter rows.")
		return lines
	}
	lines = append(lines, "This is top-down / multi-timeframe analysis. The lower-timeframe trade is kept only when its direction agrees with the last completed 30m or 60m regime bar, so the table avoids lookahead from the currently forming higher-timeframe candle.")
	lines = append(lines, "")
	lines = append(lines, "Methods tested: EMA20 slope, EMA20/EMA50 stack, MACD histogram, MACD zero-line trend, ADX/DMI, Donchian trend state, session VWAP bias, and confirmed swing structure. `swing_structure` is the mechanical Elliott-wave-like proxy: higher highs plus higher lows are bullish; lower highs plus lower lows are bearish.")
	lines = append(lines, "")

	top := append([]regimeFilterRow(nil), rows...)
	sort.Slice(top, func(i, j int) bool {
		ai := top[i].Aligned.TotalR - top[i].Base.TotalR
		aj := top[j].Aligned.TotalR - top[j].Base.TotalR
		if ai != aj {
			return ai > aj
		}
		return top[i].Aligned.TotalR > top[j].Aligned.TotalR
	})

	lines = append(lines, "### Best Improvements", "")
	lines = append(lines, "| Regime TF | Method | Entry TF | Variant | Base trades | Base R | Aligned trades | Aligned R | Aligned win | Kept | Against R | Neutral R | Missing |")
	lines = append(lines, "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
	added := 0
	for _, row := range top {
		if row.Base.Trades < 5 || row.Aligned.Trades < 2 {
			continue
		}
		lines = append(lines, regimeFilterMarkdownRow(row))
		added++
		if added >= 25 {
			break
		}
	}
	if added == 0 {
		lines = append(lines, "| - | no rows with at least 5 base trades and 2 aligned trades | | | | | | | | | | | |")
	}

	lines = append(lines, "", "### Active Candidate Rows", "")
	lines = append(lines, "| Regime TF | Method | Entry TF | Variant | Base trades | Base R | Aligned trades | Aligned R | Aligned win | Kept | Against R | Neutral R | Missing |")
	lines = append(lines, "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
	added = 0
	for _, row := range rows {
		if !isActiveRegimeCandidate(row.Key.EntryTF, row.Key.Variant) || row.Base.Trades == 0 {
			continue
		}
		lines = append(lines, regimeFilterMarkdownRow(row))
		added++
	}
	if added == 0 {
		lines = append(lines, "| - | no active candidate rows | | | | | | | | | | | |")
	}

	lines = append(lines, "")
	lines = append(lines, "Full regime-filter detail is written to `*_regime_filters.csv`.")
	return lines
}

func regimeFilterMarkdownRow(row regimeFilterRow) string {
	return fmt.Sprintf("| %dm | %s | %dm | %s | %d | %.3f | %d | %.3f | %.1f%% | %.1f%% | %.3f | %.3f | %d |",
		row.Key.RegimeTF,
		row.Key.Method,
		row.Key.EntryTF,
		row.Key.Variant,
		row.Base.Trades,
		row.Base.TotalR,
		row.Aligned.Trades,
		row.Aligned.TotalR,
		summaryWinRate(row.Aligned),
		row.KeptPct,
		row.Against.TotalR,
		row.Neutral.TotalR,
		row.Missing)
}

func isActiveRegimeCandidate(tf int, variant string) bool {
	if tf != 1 && tf != 5 && tf != 15 {
		return false
	}
	switch variant {
	case "raw_sfp", "macd_cross", "macd_zero_trend", "donchian_breakout", "donchian_volume_delta", "donchian_depth_delta", "bollinger_breakout", "bollinger_volume_delta", "rsi_reversion", "depth_delta_momentum", "vwap_reclaim", "vwap_delta_reclaim", "vwap_rejection", "vwap_delta_rejection", "orb15_breakout", "orb15_retest", "orb30_breakout", "orb30_retest", "value_rejection", "value_breakout", "opening_drive_pullback", "opening_drive_failure", "ib_acceptance", "ib_rejection", "ib_strict_acceptance", "vwap_slope_pullback", "vwap_flat_reversion", "value_reclaim", "vwap_absorption_reversal", "prior_rth_high_reclaim", "prior_rth_low_reclaim", "prior_rth_close_reclaim", "prior_rth_vwap_reclaim", "overnight_high_reclaim", "overnight_low_reclaim", "prior_rth_high_rejection", "prior_rth_low_rejection", "overnight_high_rejection", "overnight_low_rejection", "rth_open_1m_bollinger_breakout", "rth_open_1m_bollinger_volume_delta", "rth_open_1m_donchian_breakout", "rth_open_1m_or30_drive_pullback", "rth_open_1m_or30_drive_failure", "rth_open_1m_ib_rejection", "rth_open_1m_ib_strict_acceptance", "rth_open_1m_prior_rth_high_reclaim", "rth_open_1m_prior_rth_low_reclaim", "rth_open_1m_overnight_high_reclaim", "rth_open_1m_overnight_low_reclaim", "rth_lunch_1m_donchian_breakout", "rth_lunch_1m_rsi_reversion", "rth_close_5m_bollinger_breakout", "rth_lunch_5m_vwap_rejection", "rth_open_5m_ib_acceptance", "rth_open_5m_ib_rejection", "rth_open_5m_ib_strict_acceptance", "rth_open_5m_vwap_slope_pullback", "rth_lunch_5m_vwap_flat_reversion", "rth_open_5m_value_reclaim", "rth_open_5m_prior_rth_vwap_reclaim", "rth_open_5m_overnight_high_reclaim", "rth_open_5m_overnight_low_reclaim":
		return true
	default:
		return false
	}
}

func simulateApexAccount(trades []trade, contracts int, pointValue, costPoints float64, cfg analysisConfig) apexAccountSummary {
	s := apexAccountSummary{
		Contracts:       contracts,
		PlannedTrades:   len(trades),
		EndBalance:      cfg.ApexStartBalance,
		HighBalance:     cfg.ApexStartBalance,
		LowBalance:      cfg.ApexStartBalance,
		ActiveThreshold: cfg.ApexStartBalance - cfg.ApexMaxDrawdown,
		Status:          "active",
	}
	if contracts <= 0 || pointValue <= 0 {
		s.Status = "invalid"
		return s
	}

	balance := cfg.ApexStartBalance
	dayStartBalance := cfg.ApexStartBalance
	currentDay := ""
	dllPaused := false

	for _, tr := range trades {
		day := tradingDay(tr.EntryTime)
		if currentDay == "" {
			currentDay = day
		}
		if day != currentDay {
			threshold := balance - cfg.ApexMaxDrawdown
			if threshold > s.ActiveThreshold {
				s.ActiveThreshold = threshold
			}
			currentDay = day
			dayStartBalance = balance
			dllPaused = false
		}

		if s.Failed {
			break
		}
		if dllPaused {
			s.DLLSkipped++
			continue
		}

		s.TradesTaken++
		closeNet, lowDelta, highDelta := tradeAccountDeltas(tr, contracts, pointValue, costPoints)
		intratradeLow := balance + lowDelta
		intratradeHigh := balance + highDelta
		updateApexBalanceRange(&s, intratradeHigh, intratradeLow)

		if intratradeLow <= s.ActiveThreshold {
			balance = intratradeLow
			s.Failed = true
			s.FailureTime = tr.ExitTime
			s.Status = "failed_intratrade_eod"
			break
		}
		if cfg.ApexDailyLoss > 0 && intratradeLow <= dayStartBalance-cfg.ApexDailyLoss {
			s.DLLPaused = true
			s.DLLTime = tr.ExitTime
			dllPaused = true
		}

		balance += closeNet
		updateApexBalanceRange(&s, balance, balance)
		if balance >= cfg.ApexStartBalance+cfg.ApexProfitTarget && !s.TargetHit {
			s.TargetHit = true
			s.TargetTime = tr.ExitTime
		}
		if balance <= s.ActiveThreshold {
			s.Failed = true
			s.FailureTime = tr.ExitTime
			s.Status = "failed_eod"
			break
		}
		if cfg.ApexDailyLoss > 0 && balance <= dayStartBalance-cfg.ApexDailyLoss && !s.DLLPaused {
			s.DLLPaused = true
			s.DLLTime = tr.ExitTime
			dllPaused = true
		}
	}

	s.EndBalance = balance
	s.NetPnL = balance - cfg.ApexStartBalance
	if !s.Failed {
		switch {
		case s.TargetHit && balance >= cfg.ApexStartBalance+cfg.ApexProfitTarget:
			s.Status = "passed"
		case s.TargetHit:
			s.Status = "target_hit_then_gave_back"
		case s.DLLPaused:
			s.Status = "dll_paused"
		default:
			s.Status = "active"
		}
	}
	return s
}

func tradeAccountDeltas(tr trade, contracts int, pointValue, costPoints float64) (float64, float64, float64) {
	mult := pointValue * float64(contracts)
	closeNet := tr.R * tr.RiskPoints * mult
	costDollars := costPoints * mult
	adverse := tr.MAER*tr.RiskPoints*mult - costDollars
	favorable := tr.MFER*tr.RiskPoints*mult - costDollars
	if favorable < closeNet {
		favorable = closeNet
	}

	low := math.Min(closeNet, adverse)
	switch tr.Outcome {
	case "stop", "stop_same_bar":
		low = closeNet
	}
	return closeNet, low, favorable
}

func updateApexBalanceRange(s *apexAccountSummary, high, low float64) {
	if high > s.HighBalance {
		s.HighBalance = high
	}
	if low < s.LowBalance {
		s.LowBalance = low
	}
	dd := s.HighBalance - low
	if dd > s.MaxDrawdown {
		s.MaxDrawdown = dd
	}
}

func formatEventTime(s apexAccountSummary) string {
	switch {
	case s.Failed && !s.FailureTime.IsZero():
		return s.FailureTime.In(sessionLocation).Format(time.RFC3339)
	case s.TargetHit && !s.TargetTime.IsZero():
		return s.TargetTime.In(sessionLocation).Format(time.RFC3339)
	case s.DLLPaused && !s.DLLTime.IsZero():
		return s.DLLTime.In(sessionLocation).Format(time.RFC3339)
	default:
		return ""
	}
}

func appendBreakdown(lines []string, title, note string, trades []trade, bucketFn func(trade) string) []string {
	lines = append(lines, "", "## "+title, "")
	if note != "" {
		lines = append(lines, note, "")
	}
	if len(trades) == 0 {
		lines = append(lines, "No trades.")
		return lines
	}

	grouped := make(map[breakdownKey][]trade)
	keys := make([]breakdownKey, 0)
	seen := make(map[breakdownKey]bool)
	for _, tr := range trades {
		bucket := bucketFn(tr)
		if bucket == "" {
			bucket = "unknown"
		}
		key := breakdownKey{Timeframe: tr.Timeframe, Variant: tr.Variant, Bucket: bucket}
		grouped[key] = append(grouped[key], tr)
		if !seen[key] {
			keys = append(keys, key)
			seen[key] = true
		}
	}

	sort.Slice(keys, func(i, j int) bool {
		a, b := keys[i], keys[j]
		if a.Timeframe != b.Timeframe {
			return a.Timeframe < b.Timeframe
		}
		if variantRank(a.Variant) != variantRank(b.Variant) {
			return variantRank(a.Variant) < variantRank(b.Variant)
		}
		if bucketRank(a.Bucket) != bucketRank(b.Bucket) {
			return bucketRank(a.Bucket) < bucketRank(b.Bucket)
		}
		return a.Bucket < b.Bucket
	})

	lines = append(lines, "| TF | Variant | Bucket | Trades | Win rate | Avg R | Total R | PF | Max DD R | Target | Stop | Timeout |")
	lines = append(lines, "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
	for _, key := range keys {
		s := summarizeTrades(grouped[key])
		lines = append(lines, fmt.Sprintf("| %dm | %s | %s | %d | %.1f%% | %.3f | %.3f | %s | %.3f | %d | %d | %d |",
			key.Timeframe, key.Variant, key.Bucket, s.Trades, summaryWinRate(s), s.AvgR, s.TotalR, formatPF(s.ProfitFactor), s.MaxDrawdownR, s.Targets, s.Stops, s.Timeouts))
	}
	return lines
}

func variantRank(v string) int {
	switch v {
	case "raw_sfp":
		return 0
	case "volume_sfp":
		return 1
	case "delta_sfp":
		return 2
	case "volume_delta_sfp":
		return 3
	case "depth_sfp":
		return 4
	case "volume_delta_depth_sfp":
		return 5
	case "macd_cross":
		return 6
	case "macd_zero_trend":
		return 7
	case "donchian_breakout":
		return 8
	case "donchian_volume_delta":
		return 9
	case "donchian_depth_delta":
		return 10
	case "bollinger_breakout":
		return 11
	case "bollinger_volume_delta":
		return 12
	case "rsi_reversion":
		return 13
	case "depth_delta_momentum":
		return 14
	case "vwap_reclaim":
		return 15
	case "vwap_delta_reclaim":
		return 16
	case "vwap_rejection":
		return 17
	case "vwap_delta_rejection":
		return 18
	case "orb15_breakout":
		return 19
	case "orb15_retest":
		return 20
	case "orb30_breakout":
		return 21
	case "orb30_retest":
		return 22
	case "value_rejection":
		return 23
	case "value_breakout":
		return 24
	case "opening_drive_pullback":
		return 25
	case "opening_drive_failure":
		return 26
	case "ib_acceptance":
		return 27
	case "ib_rejection":
		return 28
	case "vwap_slope_pullback":
		return 29
	case "vwap_flat_reversion":
		return 30
	case "value_reclaim":
		return 31
	case "vwap_absorption_reversal":
		return 32
	case "ib_strict_acceptance":
		return 33
	case "prior_rth_high_reclaim":
		return 34
	case "prior_rth_low_reclaim":
		return 35
	case "prior_rth_close_reclaim":
		return 36
	case "prior_rth_vwap_reclaim":
		return 37
	case "overnight_high_reclaim":
		return 38
	case "overnight_low_reclaim":
		return 39
	case "prior_rth_high_rejection":
		return 40
	case "prior_rth_low_rejection":
		return 41
	case "overnight_high_rejection":
		return 42
	case "overnight_low_rejection":
		return 43
	case "mtf60_macd0_1m_macd0":
		return 44
	case "mtf60_adx_5m_rsi":
		return 45
	case "mtf60_macdhist_5m_rsi":
		return 46
	case "mtf60_macd0_5m_vwap_reject":
		return 47
	case "mtf60_adx_5m_vwap_reject":
		return 48
	case "mtf60_macd0_5m_orb15_retest":
		return 49
	case "mtf60_macd0_5m_value_reject":
		return 50
	case "rth_open_1m_bollinger_breakout":
		return 51
	case "rth_open_1m_bollinger_volume_delta":
		return 52
	case "rth_open_1m_donchian_breakout":
		return 53
	case "rth_open_1m_or30_drive_pullback":
		return 54
	case "rth_open_1m_or30_drive_failure":
		return 55
	case "rth_open_1m_ib_rejection":
		return 56
	case "rth_open_1m_ib_strict_acceptance":
		return 57
	case "rth_open_1m_prior_rth_high_reclaim":
		return 58
	case "rth_open_1m_prior_rth_low_reclaim":
		return 59
	case "rth_open_1m_overnight_high_reclaim":
		return 60
	case "rth_open_1m_overnight_low_reclaim":
		return 61
	case "rth_lunch_1m_donchian_breakout":
		return 62
	case "rth_lunch_1m_rsi_reversion":
		return 63
	case "rth_close_5m_bollinger_breakout":
		return 64
	case "rth_lunch_5m_vwap_rejection":
		return 65
	case "rth_open_5m_ib_acceptance":
		return 66
	case "rth_open_5m_ib_rejection":
		return 67
	case "rth_open_5m_ib_strict_acceptance":
		return 68
	case "rth_open_5m_vwap_slope_pullback":
		return 69
	case "rth_lunch_5m_vwap_flat_reversion":
		return 70
	case "rth_open_5m_value_reclaim":
		return 71
	case "rth_open_5m_prior_rth_vwap_reclaim":
		return 72
	case "rth_open_5m_overnight_high_reclaim":
		return 73
	case "rth_open_5m_overnight_low_reclaim":
		return 74
	default:
		return 100
	}
}

func bucketRank(b string) int {
	switch b {
	case "overnight":
		return 0
	case "rth_09_30_16_00":
		return 1
	case "rth_open_09_30_11_00":
		return 2
	case "rth_mid_11_00_11_30":
		return 3
	case "rth_lunch_11_30_13_30":
		return 4
	case "rth_afternoon_13_30_15_00":
		return 5
	case "rth_close_15_00_16_00":
		return 6
	default:
		return 100
	}
}

func sessionRollup(t time.Time) string {
	if inRTH(t) {
		return "rth_09_30_16_00"
	}
	return "overnight"
}

func sessionSegment(t time.Time) string {
	m := sessionMinute(t)
	if !inRTHMinute(m) {
		return "overnight"
	}
	switch {
	case m < 11*60:
		return "rth_open_09_30_11_00"
	case m < 11*60+30:
		return "rth_mid_11_00_11_30"
	case m < 13*60+30:
		return "rth_lunch_11_30_13_30"
	case m < 15*60:
		return "rth_afternoon_13_30_15_00"
	default:
		return "rth_close_15_00_16_00"
	}
}

func inRTH(t time.Time) bool {
	return inRTHMinute(sessionMinute(t))
}

func inRTHMinute(m int) bool {
	return m >= 9*60+30 && m < 16*60
}

func sessionMinute(t time.Time) int {
	lt := t.In(sessionLocation)
	return lt.Hour()*60 + lt.Minute()
}

func tradingDay(t time.Time) string {
	lt := t.In(sessionLocation)
	d := time.Date(lt.Year(), lt.Month(), lt.Day(), 0, 0, 0, 0, sessionLocation)
	if sessionMinute(t) >= 18*60 {
		d = d.AddDate(0, 0, 1)
	}
	return d.Format("2006-01-02")
}

func scoreSignals(bars []bar, sigs []signal, horizon int) result {
	var r result
	r.Horizon = horizon
	for _, s := range sigs {
		if s.Index+horizon >= len(bars) {
			continue
		}
		entry := bars[s.Index].Close
		exit := bars[s.Index+horizon].Close
		move := float64(s.Dir) * (exit - entry)
		var mfe, mae float64
		for j := s.Index + 1; j <= s.Index+horizon; j++ {
			fav := float64(s.Dir) * (bars[j].High - entry)
			adv := float64(s.Dir) * (bars[j].Low - entry)
			if s.Dir < 0 {
				fav = entry - bars[j].Low
				adv = entry - bars[j].High
			}
			if fav > mfe {
				mfe = fav
			}
			if adv < mae {
				mae = adv
			}
		}
		r.Signals++
		if move > 0 {
			r.Wins++
		}
		r.AvgMove += move
		r.AvgMFE += mfe
		r.AvgMAE += mae
	}
	if r.Signals > 0 {
		n := float64(r.Signals)
		r.AvgMove /= n
		r.AvgMFE /= n
		r.AvgMAE /= n
	}
	return r
}
