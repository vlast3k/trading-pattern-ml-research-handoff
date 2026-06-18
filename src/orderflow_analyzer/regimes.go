package main

import (
	"math"
	"sort"
	"time"
)

func buildRegimeFilterRows(trades []trade, oneMinuteBars []bar) []regimeFilterRow {
	if len(trades) == 0 || len(oneMinuteBars) == 0 {
		return nil
	}

	regimeTFs := []int{30, 60}
	methods := []string{
		"ema20_slope",
		"ema20_ema50",
		"macd_hist",
		"macd_zero_trend",
		"adx_dmi",
		"donchian20",
		"session_vwap",
		"swing_structure",
	}

	out := make([]regimeFilterRow, 0)
	for _, regimeTF := range regimeTFs {
		htfBars := resample(oneMinuteBars, regimeTF)
		if len(htfBars) < 10 {
			continue
		}
		for _, method := range methods {
			regimes := buildRegimePoints(htfBars, regimeTF, method)
			if len(regimes) == 0 {
				continue
			}
			rows := buildRowsForRegime(trades, regimes, regimeTF, method)
			out = append(out, rows...)
		}
	}

	sort.Slice(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.Key.RegimeTF != b.Key.RegimeTF {
			return a.Key.RegimeTF < b.Key.RegimeTF
		}
		if a.Key.Method != b.Key.Method {
			return a.Key.Method < b.Key.Method
		}
		if a.Key.EntryTF != b.Key.EntryTF {
			return a.Key.EntryTF < b.Key.EntryTF
		}
		if variantRank(a.Key.Variant) != variantRank(b.Key.Variant) {
			return variantRank(a.Key.Variant) < variantRank(b.Key.Variant)
		}
		return a.Key.Variant < b.Key.Variant
	})
	return out
}

func buildRegimeTradeRows(trades []trade, oneMinuteBars []bar) []regimeTradeRow {
	if len(trades) == 0 || len(oneMinuteBars) == 0 {
		return nil
	}

	regimeTFs := []int{30, 60}
	methods := []string{
		"ema20_slope",
		"ema20_ema50",
		"macd_hist",
		"macd_zero_trend",
		"adx_dmi",
		"donchian20",
		"session_vwap",
		"swing_structure",
	}

	out := make([]regimeTradeRow, 0)
	for _, regimeTF := range regimeTFs {
		htfBars := resample(oneMinuteBars, regimeTF)
		if len(htfBars) < 10 {
			continue
		}
		for _, method := range methods {
			regimes := buildRegimePoints(htfBars, regimeTF, method)
			if len(regimes) == 0 {
				continue
			}
			for _, tr := range trades {
				if tr.Timeframe >= regimeTF {
					continue
				}
				row := regimeTradeRow{
					RegimeTF:  regimeTF,
					Method:    method,
					Alignment: "missing",
					Trade:     tr,
				}
				regime, ok := lookupCompletedRegime(regimes, tr.SignalTime, regimeTF)
				if ok {
					row.RegimeTime = regime.Time
					row.RegimeDir = regime.Dir
					row.RegimeLabel = regime.Label
					row.RegimeStrength = regime.Strength
					switch {
					case regime.Dir == 0:
						row.Alignment = "neutral"
					case regime.Dir == tr.Dir:
						row.Alignment = "aligned"
					case regime.Dir == -tr.Dir:
						row.Alignment = "against"
					default:
						row.Alignment = "neutral"
					}
				}
				out = append(out, row)
			}
		}
	}

	sort.SliceStable(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.RegimeTF != b.RegimeTF {
			return a.RegimeTF < b.RegimeTF
		}
		if a.Method != b.Method {
			return a.Method < b.Method
		}
		if a.Trade.Timeframe != b.Trade.Timeframe {
			return a.Trade.Timeframe < b.Trade.Timeframe
		}
		if variantRank(a.Trade.Variant) != variantRank(b.Trade.Variant) {
			return variantRank(a.Trade.Variant) < variantRank(b.Trade.Variant)
		}
		if a.Trade.Variant != b.Trade.Variant {
			return a.Trade.Variant < b.Trade.Variant
		}
		return a.Trade.EntryTime.Before(b.Trade.EntryTime)
	})
	return out
}

func buildRowsForRegime(trades []trade, regimes []regimePoint, regimeTF int, method string) []regimeFilterRow {
	type buckets struct {
		base     []trade
		aligned  []trade
		against  []trade
		neutral  []trade
		missing  int
		strength float64
		strN     int
	}

	grouped := make(map[riskBudgetKey]*buckets)
	var keys []riskBudgetKey
	seen := make(map[riskBudgetKey]bool)
	for _, tr := range trades {
		if tr.Timeframe >= regimeTF {
			continue
		}
		key := riskBudgetKey{Timeframe: tr.Timeframe, Variant: tr.Variant}
		b := grouped[key]
		if b == nil {
			b = &buckets{}
			grouped[key] = b
		}
		if !seen[key] {
			keys = append(keys, key)
			seen[key] = true
		}
		b.base = append(b.base, tr)

		regime, ok := lookupCompletedRegime(regimes, tr.SignalTime, regimeTF)
		if !ok {
			b.missing++
			continue
		}
		if regime.Strength > 0 {
			b.strength += regime.Strength
			b.strN++
		}
		switch {
		case regime.Dir == 0:
			b.neutral = append(b.neutral, tr)
		case regime.Dir == tr.Dir:
			b.aligned = append(b.aligned, tr)
		case regime.Dir == -tr.Dir:
			b.against = append(b.against, tr)
		default:
			b.neutral = append(b.neutral, tr)
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
		return a.Variant < b.Variant
	})

	rows := make([]regimeFilterRow, 0, len(keys))
	for _, key := range keys {
		b := grouped[key]
		sortTradesByEntry(b.base)
		sortTradesByEntry(b.aligned)
		sortTradesByEntry(b.against)
		sortTradesByEntry(b.neutral)
		row := regimeFilterRow{
			Key: regimeFilterKey{
				RegimeTF: regimeTF,
				Method:   method,
				EntryTF:  key.Timeframe,
				Variant:  key.Variant,
			},
			Base:    summarizeTrades(b.base),
			Aligned: summarizeTrades(b.aligned),
			Against: summarizeTrades(b.against),
			Neutral: summarizeTrades(b.neutral),
			Missing: b.missing,
		}
		if row.Base.Trades > 0 {
			row.KeptPct = 100 * float64(row.Aligned.Trades) / float64(row.Base.Trades)
		}
		if b.strN > 0 {
			row.AvgPower = b.strength / float64(b.strN)
		}
		rows = append(rows, row)
	}
	return rows
}

func sortTradesByEntry(trades []trade) {
	sort.SliceStable(trades, func(i, j int) bool {
		return trades[i].EntryTime.Before(trades[j].EntryTime)
	})
}

func buildDayRegimes(bars []bar, rollingLookback int) []dayRegime {
	if rollingLookback < 1 {
		rollingLookback = 5
	}
	byDay := make(map[string][]bar)
	seen := make(map[string]bool)
	var days []string
	for _, b := range bars {
		if b.Time.IsZero() {
			continue
		}
		day := tradingDay(b.Time)
		if !seen[day] {
			seen[day] = true
			days = append(days, day)
		}
		byDay[day] = append(byDay[day], b)
	}
	sort.Strings(days)

	regimes := make([]dayRegime, 0, len(days))
	var priorRTHClose float64
	for _, day := range days {
		dayBars := byDay[day]
		sort.SliceStable(dayBars, func(i, j int) bool {
			return dayBars[i].Time.Before(dayBars[j].Time)
		})
		rthBars := filterRTHBars(dayBars)
		if len(rthBars) == 0 {
			continue
		}
		first := rthBars[0]
		dr := dayRegime{
			Day:        day,
			OpenTime:   first.Time,
			Complete:   true,
			PriorClose: priorRTHClose,
			Open:       first.Open,
		}
		if dr.Open == 0 {
			dr.Open = first.Close
		}
		if priorRTHClose > 0 && dr.Open > 0 {
			dr.GapPoints = dr.Open - priorRTHClose
			dr.GapPct = 100 * dr.GapPoints / priorRTHClose
		}
		_, firstMinuteOK := openingWindowStartsOnTime(rthBars)
		dr.OR5Range, dr.OR5Return, dr.OR5Volume, dr.OR5Bars, _ = openingWindowStats(rthBars, 5)
		dr.OR15Range, dr.OR15Return, dr.OR15Volume, dr.OR15Bars, _ = openingWindowStats(rthBars, 15)
		dr.OR30Range, dr.OR30Return, dr.OR30Volume, dr.OR30Bars, _ = openingWindowStats(rthBars, 30)
		dr.Complete = firstMinuteOK && dr.OR5Bars >= 3 && dr.OR15Bars >= 10 && dr.OR30Bars >= 20
		regimes = append(regimes, dr)
		priorRTHClose = rthBars[len(rthBars)-1].Close
	}

	for i := range regimes {
		rangeVals := make([]float64, 0, rollingLookback)
		volumeVals := make([]float64, 0, rollingLookback)
		for j := i - 1; j >= 0 && len(rangeVals) < rollingLookback; j-- {
			if regimes[j].OR30Range > 0 {
				rangeVals = append(rangeVals, regimes[j].OR30Range)
			}
			if regimes[j].OR30Volume > 0 {
				volumeVals = append(volumeVals, float64(regimes[j].OR30Volume))
			}
		}
		regimes[i].OR30RangeZ = zScore(regimes[i].OR30Range, rangeVals)
		regimes[i].OR30VolumeZ = zScore(float64(regimes[i].OR30Volume), volumeVals)
		classifyDayRegime(&regimes[i])
	}
	return regimes
}

func filterRTHBars(bars []bar) []bar {
	out := make([]bar, 0, len(bars))
	for _, b := range bars {
		if inRTH(b.Time) && isValidBar(b) {
			out = append(out, b)
		}
	}
	return out
}

func openingWindowStartsOnTime(rthBars []bar) (int, bool) {
	if len(rthBars) == 0 {
		return 0, false
	}
	firstMinute := sessionMinute(rthBars[0].Time)
	return firstMinute, firstMinute <= 9*60+32
}

func openingWindowStats(rthBars []bar, minutes int) (rangePoints, returnPoints float64, volume int64, count int, ok bool) {
	if minutes <= 0 || len(rthBars) == 0 {
		return 0, 0, 0, 0, false
	}
	start := 9*60 + 30
	end := start + minutes
	var open, close, high, low float64
	for _, b := range rthBars {
		m := sessionMinute(b.Time)
		if m < start || m >= end {
			continue
		}
		if !ok {
			open = b.Open
			if open == 0 {
				open = b.Close
			}
			high = b.High
			low = b.Low
			ok = true
		}
		if b.High > high {
			high = b.High
		}
		if b.Low < low || low == 0 {
			low = b.Low
		}
		close = b.Close
		volume += b.Volume
		count++
	}
	if !ok || high <= low || open == 0 || close == 0 {
		return 0, 0, volume, count, ok
	}
	return high - low, close - open, volume, count, true
}

func zScore(value float64, prior []float64) float64 {
	if len(prior) < 3 {
		return 0
	}
	var sum float64
	for _, v := range prior {
		sum += v
	}
	mean := sum / float64(len(prior))
	var ss float64
	for _, v := range prior {
		d := v - mean
		ss += d * d
	}
	std := math.Sqrt(ss / float64(len(prior)))
	if std <= 0 {
		return 0
	}
	return (value - mean) / std
}

func classifyDayRegime(dr *dayRegime) {
	if !dr.Complete {
		dr.GapLabel = "opening_data_incomplete"
		dr.BiasLabel = "opening_data_incomplete"
		dr.RangeLabel = "opening_data_incomplete"
		dr.VolumeLabel = "opening_data_incomplete"
		dr.RegimeLabel = "incomplete_open"
		return
	}

	dr.GapLabel = "gap_unknown"
	gapThreshold := math.Max(0.25*dr.OR30Range, 0.25)
	if dr.PriorClose > 0 && dr.Open > 0 {
		switch {
		case math.Abs(dr.GapPoints) < gapThreshold:
			dr.GapLabel = "flat_gap"
		case dr.GapPoints > 0:
			dr.GapLabel = "gap_up"
		default:
			dr.GapLabel = "gap_down"
		}
	}

	returnThreshold := math.Max(0.20*dr.OR30Range, 0.25)
	switch {
	case dr.OR30Return > returnThreshold:
		dr.BiasLabel = "open_drive_up"
	case dr.OR30Return < -returnThreshold:
		dr.BiasLabel = "open_drive_down"
	default:
		dr.BiasLabel = "two_way_open"
	}

	switch {
	case dr.OR30RangeZ >= 1.0:
		dr.RangeLabel = "wide_opening_range"
	case dr.OR30RangeZ <= -0.75:
		dr.RangeLabel = "narrow_opening_range"
	default:
		dr.RangeLabel = "normal_opening_range"
	}

	switch {
	case dr.OR30VolumeZ >= 1.0:
		dr.VolumeLabel = "high_opening_volume"
	case dr.OR30VolumeZ <= -0.75:
		dr.VolumeLabel = "low_opening_volume"
	default:
		dr.VolumeLabel = "normal_opening_volume"
	}

	highEnergy := dr.RangeLabel == "wide_opening_range" || dr.VolumeLabel == "high_opening_volume" ||
		(dr.BiasLabel == "open_drive_up" && dr.GapLabel == "gap_up") ||
		(dr.BiasLabel == "open_drive_down" && dr.GapLabel == "gap_down")

	switch {
	case dr.BiasLabel == "open_drive_up" && highEnergy:
		dr.RegimeLabel = "vvg_trend_up"
	case dr.BiasLabel == "open_drive_down" && highEnergy:
		dr.RegimeLabel = "vvg_trend_down"
	case dr.BiasLabel == "open_drive_up":
		dr.RegimeLabel = "drift_up"
	case dr.BiasLabel == "open_drive_down":
		dr.RegimeLabel = "drift_down"
	case dr.RangeLabel == "narrow_opening_range" || dr.VolumeLabel == "low_opening_volume":
		dr.RegimeLabel = "rotation"
	case dr.RangeLabel == "wide_opening_range" || dr.VolumeLabel == "high_opening_volume":
		dr.RegimeLabel = "volatile_two_way"
	default:
		dr.RegimeLabel = "neutral_open"
	}
}

func buildDayRegimeStrategyRows(trades []trade, regimes []dayRegime, pointValue float64) []dayRegimeStrategyRow {
	regimeByDay := dayRegimeByDay(regimes)
	grouped := make(map[dayRegimeStrategyKey][]trade)
	var keys []dayRegimeStrategyKey
	seen := make(map[dayRegimeStrategyKey]bool)
	for _, tr := range trades {
		if !isDayRegimeEligibleTrade(tr) {
			continue
		}
		dr, ok := regimeByDay[tradingDay(tr.EntryTime)]
		if !ok || !dr.Complete || dr.RegimeLabel == "" {
			continue
		}
		key := dayRegimeStrategyKey{Regime: dr.RegimeLabel, Timeframe: tr.Timeframe, Variant: tr.Variant}
		grouped[key] = append(grouped[key], tr)
		if !seen[key] {
			keys = append(keys, key)
			seen[key] = true
		}
	}
	rows := make([]dayRegimeStrategyRow, 0, len(keys))
	for _, key := range keys {
		sortTradesByEntry(grouped[key])
		rows = append(rows, dayRegimeStrategyRow{Key: key, Summary: summarizeTradesDollars(grouped[key], pointValue)})
	}
	sort.Slice(rows, func(i, j int) bool {
		a, b := rows[i], rows[j]
		if a.Key.Regime != b.Key.Regime {
			return a.Key.Regime < b.Key.Regime
		}
		if a.Summary.Summary.TotalR != b.Summary.Summary.TotalR {
			return a.Summary.Summary.TotalR > b.Summary.Summary.TotalR
		}
		if a.Key.Timeframe != b.Key.Timeframe {
			return a.Key.Timeframe < b.Key.Timeframe
		}
		return a.Key.Variant < b.Key.Variant
	})
	return rows
}

func buildDayRegimeSelectorRows(trades []trade, regimes []dayRegime, pointValue float64) []dayRegimeSelectorRow {
	if len(regimes) == 0 {
		return nil
	}
	regimeByDay := dayRegimeByDay(regimes)
	dayTrades := make(map[string]map[riskBudgetKey][]trade)
	for _, tr := range trades {
		if !isDayRegimeEligibleTrade(tr) || !isDaySelectorCandidate(tr.Timeframe, tr.Variant) {
			continue
		}
		day := tradingDay(tr.EntryTime)
		if _, ok := regimeByDay[day]; !ok {
			continue
		}
		key := riskBudgetKey{Timeframe: tr.Timeframe, Variant: tr.Variant}
		if dayTrades[day] == nil {
			dayTrades[day] = make(map[riskBudgetKey][]trade)
		}
		dayTrades[day][key] = append(dayTrades[day][key], tr)
	}

	candidates := daySelectorCandidatesFromTrades(dayTrades)
	rows := make([]dayRegimeSelectorRow, 0, len(regimes))
	for i, dr := range regimes {
		if !dr.Complete || dr.RegimeLabel == "" {
			continue
		}
		if key, prior, ok := bestPriorCandidate(regimes[:i], dayTrades, candidates, pointValue, dr.RegimeLabel, 3); ok {
			current := append([]trade(nil), dayTrades[dr.Day][key]...)
			sortTradesByEntry(current)
			rows = append(rows, dayRegimeSelectorRow{
				Day:         dr.Day,
				Regime:      dr.RegimeLabel,
				Mode:        "same_regime_only",
				Source:      "same_regime_prior",
				Timeframe:   key.Timeframe,
				Variant:     key.Variant,
				PriorTrades: prior.Summary.Trades,
				PriorTotalR: prior.Summary.TotalR,
				PriorAvgR:   prior.Summary.AvgR,
				Summary:     summarizeTradesDollars(current, pointValue),
			})
		}
		key, prior, source, ok := selectDayRegimeCandidate(regimes[:i], dayTrades, candidates, dr.RegimeLabel, pointValue)
		if !ok {
			continue
		}
		current := append([]trade(nil), dayTrades[dr.Day][key]...)
		sortTradesByEntry(current)
		rows = append(rows, dayRegimeSelectorRow{
			Day:         dr.Day,
			Regime:      dr.RegimeLabel,
			Mode:        "fallback_enabled",
			Source:      source,
			Timeframe:   key.Timeframe,
			Variant:     key.Variant,
			PriorTrades: prior.Summary.Trades,
			PriorTotalR: prior.Summary.TotalR,
			PriorAvgR:   prior.Summary.AvgR,
			Summary:     summarizeTradesDollars(current, pointValue),
		})
	}
	return rows
}

func dayRegimeByDay(regimes []dayRegime) map[string]dayRegime {
	out := make(map[string]dayRegime, len(regimes))
	for _, dr := range regimes {
		out[dr.Day] = dr
	}
	return out
}

func daySelectorCandidatesFromTrades(dayTrades map[string]map[riskBudgetKey][]trade) []riskBudgetKey {
	seen := make(map[riskBudgetKey]bool)
	var out []riskBudgetKey
	for _, byKey := range dayTrades {
		for key := range byKey {
			if !seen[key] {
				seen[key] = true
				out = append(out, key)
			}
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Timeframe != out[j].Timeframe {
			return out[i].Timeframe < out[j].Timeframe
		}
		if variantRank(out[i].Variant) != variantRank(out[j].Variant) {
			return variantRank(out[i].Variant) < variantRank(out[j].Variant)
		}
		return out[i].Variant < out[j].Variant
	})
	return out
}

func selectDayRegimeCandidate(priorRegimes []dayRegime, dayTrades map[string]map[riskBudgetKey][]trade, candidates []riskBudgetKey, targetRegime string, pointValue float64) (riskBudgetKey, dollarSummary, string, bool) {
	if len(candidates) == 0 || len(priorRegimes) == 0 {
		return riskBudgetKey{}, dollarSummary{}, "", false
	}
	if key, summary, ok := bestPriorCandidate(priorRegimes, dayTrades, candidates, pointValue, targetRegime, 3); ok {
		return key, summary, "same_regime_prior", true
	}
	if key, summary, ok := bestPriorCandidate(priorRegimes, dayTrades, candidates, pointValue, "", 5); ok {
		return key, summary, "all_prior_fallback", true
	}
	return riskBudgetKey{}, dollarSummary{}, "", false
}

func bestPriorCandidate(priorRegimes []dayRegime, dayTrades map[string]map[riskBudgetKey][]trade, candidates []riskBudgetKey, pointValue float64, requiredRegime string, minTrades int) (riskBudgetKey, dollarSummary, bool) {
	var bestKey riskBudgetKey
	var best dollarSummary
	found := false
	for _, key := range candidates {
		var prior []trade
		for _, dr := range priorRegimes {
			if requiredRegime != "" && dr.RegimeLabel != requiredRegime {
				continue
			}
			prior = append(prior, dayTrades[dr.Day][key]...)
		}
		sortTradesByEntry(prior)
		s := summarizeTradesDollars(prior, pointValue)
		if s.Summary.Trades < minTrades || s.Summary.TotalR <= 0 {
			continue
		}
		if !found || daySelectorScore(s) > daySelectorScore(best) ||
			(daySelectorScore(s) == daySelectorScore(best) && s.Summary.TotalR > best.Summary.TotalR) {
			bestKey = key
			best = s
			found = true
		}
	}
	return bestKey, best, found
}

func daySelectorScore(s dollarSummary) float64 {
	if s.Summary.Trades == 0 {
		return math.Inf(-1)
	}
	return s.Summary.AvgR*math.Sqrt(float64(s.Summary.Trades)) - 0.03*s.Summary.MaxDrawdownR
}

func isDayRegimeEligibleTrade(tr trade) bool {
	if sessionRollup(tr.EntryTime) != "rth_09_30_16_00" {
		return false
	}
	return sessionMinute(tr.EntryTime) >= 10*60
}

func isDaySelectorCandidate(tf int, variant string) bool {
	if tf != 1 && tf != 5 && tf != 15 {
		return false
	}
	switch variant {
	case "raw_sfp", "volume_sfp", "volume_delta_sfp", "macd_cross", "macd_zero_trend",
		"donchian_breakout", "donchian_volume_delta", "bollinger_breakout", "bollinger_volume_delta",
		"rsi_reversion", "vwap_reclaim", "vwap_delta_reclaim", "vwap_rejection", "vwap_delta_rejection",
		"value_rejection", "value_breakout", "opening_drive_pullback", "opening_drive_failure",
		"ib_acceptance", "ib_rejection", "ib_strict_acceptance", "vwap_slope_pullback", "vwap_flat_reversion",
		"value_reclaim", "vwap_absorption_reversal", "prior_rth_high_reclaim", "prior_rth_low_reclaim",
		"prior_rth_close_reclaim", "prior_rth_vwap_reclaim", "overnight_high_reclaim", "overnight_low_reclaim",
		"prior_rth_high_rejection", "prior_rth_low_rejection", "overnight_high_rejection", "overnight_low_rejection",
		"mtf60_macd0_1m_macd0", "mtf60_adx_5m_rsi",
		"mtf60_macdhist_5m_rsi", "mtf60_macd0_5m_vwap_reject", "mtf60_adx_5m_vwap_reject",
		"rth_open_1m_bollinger_breakout", "rth_open_1m_bollinger_volume_delta",
		"rth_open_1m_donchian_breakout", "rth_open_1m_or30_drive_pullback",
		"rth_open_1m_or30_drive_failure", "rth_open_1m_ib_rejection",
		"rth_open_1m_ib_strict_acceptance", "rth_open_1m_prior_rth_high_reclaim",
		"rth_open_1m_prior_rth_low_reclaim", "rth_open_1m_overnight_high_reclaim",
		"rth_open_1m_overnight_low_reclaim",
		"rth_lunch_1m_rsi_reversion", "rth_lunch_5m_vwap_rejection",
		"rth_open_5m_ib_acceptance", "rth_open_5m_ib_rejection",
		"rth_open_5m_vwap_slope_pullback", "rth_lunch_5m_vwap_flat_reversion",
		"rth_open_5m_value_reclaim", "rth_open_5m_ib_strict_acceptance",
		"rth_open_5m_prior_rth_vwap_reclaim", "rth_open_5m_overnight_high_reclaim",
		"rth_open_5m_overnight_low_reclaim":
		return true
	default:
		return false
	}
}

func summarizeTradesDollars(trades []trade, pointValue float64) dollarSummary {
	sortTradesByEntry(trades)
	out := dollarSummary{Summary: summarizeTrades(trades)}
	var equity, peak float64
	dayPnL := make(map[string]float64)
	for _, tr := range trades {
		pnl := tradeDollars(tr, pointValue)
		out.Dollars += pnl
		equity += pnl
		if equity > peak {
			peak = equity
		}
		if dd := peak - equity; dd > out.MaxDrawdown {
			out.MaxDrawdown = dd
		}
		dayPnL[tradingDay(tr.EntryTime)] += pnl
	}
	out.Days = len(dayPnL)
	for _, pnl := range dayPnL {
		if pnl > 0 {
			out.PositiveDays++
		} else if pnl < 0 {
			out.NegativeDays++
		}
	}
	return out
}

func tradeDollars(tr trade, pointValue float64) float64 {
	if pointValue <= 0 {
		return 0
	}
	return tr.R * tr.RiskPoints * pointValue
}

func lookupCompletedRegime(regimes []regimePoint, signalTime time.Time, regimeTF int) (regimePoint, bool) {
	if len(regimes) == 0 || signalTime.IsZero() || regimeTF <= 0 {
		return regimePoint{}, false
	}
	cutoff := signalTime.Add(-time.Duration(regimeTF) * time.Minute)
	idx := sort.Search(len(regimes), func(i int) bool {
		return regimes[i].Time.After(cutoff)
	})
	if idx == 0 {
		return regimePoint{}, false
	}
	return regimes[idx-1], true
}

func buildRegimePoints(bars []bar, tf int, method string) []regimePoint {
	switch method {
	case "ema20_slope":
		return buildEMA20SlopeRegime(bars, tf, method)
	case "ema20_ema50":
		return buildEMAStackRegime(bars, tf, method)
	case "macd_hist":
		return buildMACDRegime(bars, tf, method, false)
	case "macd_zero_trend":
		return buildMACDRegime(bars, tf, method, true)
	case "adx_dmi":
		return buildADXRegime(bars, tf, method)
	case "donchian20":
		return buildDonchianRegime(bars, tf, method)
	case "session_vwap":
		return buildSessionVWAPRegime(bars, tf, method)
	case "swing_structure":
		return buildSwingStructureRegime(bars, tf, method)
	default:
		return nil
	}
}

func closesFromBars(bars []bar) []float64 {
	out := make([]float64, len(bars))
	for i, b := range bars {
		out[i] = b.Close
	}
	return out
}

func buildEMA20SlopeRegime(bars []bar, tf int, method string) []regimePoint {
	closes := closesFromBars(bars)
	ema := emaSeries(closes, 20)
	atr := atrSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	for i := 22; i < len(bars); i++ {
		dir := 0
		switch {
		case bars[i].Close > ema[i] && ema[i] > ema[i-3]:
			dir = 1
		case bars[i].Close < ema[i] && ema[i] < ema[i-3]:
			dir = -1
		}
		strength := normalizedDistance(math.Abs(bars[i].Close-ema[i])+math.Abs(ema[i]-ema[i-3]), atr[i])
		points = append(points, regimePoint{Time: bars[i].Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: strength})
	}
	return points
}

func buildEMAStackRegime(bars []bar, tf int, method string) []regimePoint {
	closes := closesFromBars(bars)
	ema20 := emaSeries(closes, 20)
	ema50 := emaSeries(closes, 50)
	atr := atrSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	for i := 52; i < len(bars); i++ {
		dir := 0
		switch {
		case bars[i].Close > ema20[i] && ema20[i] > ema50[i]:
			dir = 1
		case bars[i].Close < ema20[i] && ema20[i] < ema50[i]:
			dir = -1
		}
		strength := normalizedDistance(math.Abs(ema20[i]-ema50[i]), atr[i])
		points = append(points, regimePoint{Time: bars[i].Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: strength})
	}
	return points
}

func buildMACDRegime(bars []bar, tf int, method string, requireZeroTrend bool) []regimePoint {
	if len(bars) < 40 {
		return nil
	}
	closes := closesFromBars(bars)
	fast := emaSeries(closes, 12)
	slow := emaSeries(closes, 26)
	macdLine := make([]float64, len(bars))
	for i := range bars {
		macdLine[i] = fast[i] - slow[i]
	}
	signalLine := emaSeries(macdLine, 9)
	atr := atrSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	for i := 35; i < len(bars); i++ {
		hist := macdLine[i] - signalLine[i]
		dir := 0
		if requireZeroTrend {
			if macdLine[i] > 0 && hist > 0 {
				dir = 1
			} else if macdLine[i] < 0 && hist < 0 {
				dir = -1
			}
		} else if hist > 0 {
			dir = 1
		} else if hist < 0 {
			dir = -1
		}
		points = append(points, regimePoint{Time: bars[i].Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: normalizedDistance(math.Abs(hist), atr[i])})
	}
	return points
}

func buildADXRegime(bars []bar, tf int, method string) []regimePoint {
	plusDI, minusDI, adx := dmiADXSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	for i := 28; i < len(bars); i++ {
		dir := 0
		if adx[i] >= 18 {
			if plusDI[i] > minusDI[i] {
				dir = 1
			} else if minusDI[i] > plusDI[i] {
				dir = -1
			}
		}
		points = append(points, regimePoint{Time: bars[i].Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: adx[i]})
	}
	return points
}

func dmiADXSeries(bars []bar, period int) ([]float64, []float64, []float64) {
	plusDI := make([]float64, len(bars))
	minusDI := make([]float64, len(bars))
	adx := make([]float64, len(bars))
	if len(bars) < 2 || period <= 0 {
		return plusDI, minusDI, adx
	}
	tr := make([]float64, len(bars))
	plusDM := make([]float64, len(bars))
	minusDM := make([]float64, len(bars))
	for i := 1; i < len(bars); i++ {
		upMove := bars[i].High - bars[i-1].High
		downMove := bars[i-1].Low - bars[i].Low
		if upMove > downMove && upMove > 0 {
			plusDM[i] = upMove
		}
		if downMove > upMove && downMove > 0 {
			minusDM[i] = downMove
		}
		tr[i] = math.Max(bars[i].High-bars[i].Low, math.Max(math.Abs(bars[i].High-bars[i-1].Close), math.Abs(bars[i].Low-bars[i-1].Close)))
	}
	atr := smaSeries(tr, period)
	plusMA := smaSeries(plusDM, period)
	minusMA := smaSeries(minusDM, period)
	dx := make([]float64, len(bars))
	for i := period; i < len(bars); i++ {
		if atr[i] <= 0 {
			continue
		}
		plusDI[i] = 100 * plusMA[i] / atr[i]
		minusDI[i] = 100 * minusMA[i] / atr[i]
		sum := plusDI[i] + minusDI[i]
		if sum > 0 {
			dx[i] = 100 * math.Abs(plusDI[i]-minusDI[i]) / sum
		}
	}
	adx = smaSeries(dx, period)
	return plusDI, minusDI, adx
}

func buildDonchianRegime(bars []bar, tf int, method string) []regimePoint {
	const lookback = 20
	atr := atrSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	for i := lookback; i < len(bars); i++ {
		prevHigh := bars[i-lookback].High
		prevLow := bars[i-lookback].Low
		for j := i - lookback; j < i; j++ {
			if bars[j].High > prevHigh {
				prevHigh = bars[j].High
			}
			if bars[j].Low < prevLow {
				prevLow = bars[j].Low
			}
		}
		dir := 0
		dist := 0.0
		if bars[i].Close > prevHigh {
			dir = 1
			dist = bars[i].Close - prevHigh
		} else if bars[i].Close < prevLow {
			dir = -1
			dist = prevLow - bars[i].Close
		}
		points = append(points, regimePoint{Time: bars[i].Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: normalizedDistance(dist, atr[i])})
	}
	return points
}

func buildSessionVWAPRegime(bars []bar, tf int, method string) []regimePoint {
	atr := atrSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	var currentDay string
	var pv, vol float64
	var prevVWAP float64
	for i, b := range bars {
		day := tradingDay(b.Time)
		if day != currentDay {
			currentDay = day
			pv = 0
			vol = 0
			prevVWAP = 0
		}
		typical := (b.High + b.Low + b.Close) / 3
		barVol := float64(b.Volume)
		if barVol <= 0 {
			barVol = 1
		}
		pv += typical * barVol
		vol += barVol
		vwap := pv / vol
		dir := 0
		if i >= 14 {
			if b.Close > vwap && (prevVWAP == 0 || vwap >= prevVWAP) {
				dir = 1
			} else if b.Close < vwap && (prevVWAP == 0 || vwap <= prevVWAP) {
				dir = -1
			}
		}
		points = append(points, regimePoint{Time: b.Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: normalizedDistance(math.Abs(b.Close-vwap), atr[i])})
		prevVWAP = vwap
	}
	return points
}

func buildSwingStructureRegime(bars []bar, tf int, method string) []regimePoint {
	const left = 2
	const right = 2
	atr := atrSeries(bars, 14)
	points := make([]regimePoint, 0, len(bars))
	var high1, high2, low1, low2 float64
	for i := 0; i < len(bars); i++ {
		pivotIdx := i - right
		if pivotIdx >= left {
			if confirmedPivotHigh(bars, pivotIdx, left, right) {
				high2 = high1
				high1 = bars[pivotIdx].High
			}
			if confirmedPivotLow(bars, pivotIdx, left, right) {
				low2 = low1
				low1 = bars[pivotIdx].Low
			}
		}
		dir := 0
		power := 0.0
		if high2 > 0 && low2 > 0 && high1 > 0 && low1 > 0 {
			if high1 > high2 && low1 > low2 {
				dir = 1
				power = (high1 - high2) + (low1 - low2)
			} else if high1 < high2 && low1 < low2 {
				dir = -1
				power = (high2 - high1) + (low2 - low1)
			}
		}
		points = append(points, regimePoint{Time: bars[i].Time, TF: tf, Method: method, Dir: dir, Label: regimeLabel(dir), Strength: normalizedDistance(power, atr[i])})
	}
	return points
}

func confirmedPivotHigh(bars []bar, idx, left, right int) bool {
	h := bars[idx].High
	for j := idx - left; j <= idx+right; j++ {
		if j == idx || j < 0 || j >= len(bars) {
			continue
		}
		if bars[j].High >= h {
			return false
		}
	}
	return true
}

func confirmedPivotLow(bars []bar, idx, left, right int) bool {
	l := bars[idx].Low
	for j := idx - left; j <= idx+right; j++ {
		if j == idx || j < 0 || j >= len(bars) {
			continue
		}
		if bars[j].Low <= l {
			return false
		}
	}
	return true
}

func normalizedDistance(value, denom float64) float64 {
	if denom <= 0 {
		return 0
	}
	return value / denom
}

func regimeLabel(dir int) string {
	switch {
	case dir > 0:
		return "bullish"
	case dir < 0:
		return "bearish"
	default:
		return "neutral"
	}
}
