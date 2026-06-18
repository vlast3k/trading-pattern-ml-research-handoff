package main

import (
	"fmt"
	"hash/fnv"
	"math"
	"sort"
	"strings"
	"time"
)

func simulateTrades(instrument string, bars []bar, sigs []signal, variant string, timeframe int, cfg analysisConfig, costPoints float64) []trade {
	profile := advisorProfile{Name: "auto_" + cfg.FillMode, DelayBars: 0, MissRate: 0, ExpiryBars: 1 << 30, MaxChaseR: 0}
	return simulateTradesWithProfile(instrument, bars, sigs, variant, timeframe, cfg, costPoints, profile).Trades
}

func simulateTradesWithProfile(instrument string, bars []bar, sigs []signal, variant string, timeframe int, cfg analysisConfig, costPoints float64, profile advisorProfile) tradeSimResult {
	result := tradeSimResult{Signals: len(sigs), Trades: make([]trade, 0, len(sigs))}
	if cfg.RR <= 0 || cfg.MaxHold <= 0 || cfg.TickSize <= 0 {
		return result
	}
	if profile.DelayBars < 0 {
		profile.DelayBars = 0
	}
	fillMode := normalizeFillMode(cfg.FillMode)
	slippage := cfg.SlippageTicks * cfg.TickSize
	for _, s := range sigs {
		if s.Index < 0 || s.Index >= len(bars) {
			continue
		}
		if profile.MissRate > 0 && deterministicSignalPercent(s, variant, timeframe) < profile.MissRate {
			result.Missed++
			continue
		}
		if profile.ExpiryBars >= 0 && profile.DelayBars > profile.ExpiryBars {
			result.Expired++
			continue
		}
		entryIdx, firstExitIdx := entryAndFirstExitIndex(s.Index, profile.DelayBars, fillMode)
		if entryIdx >= len(bars) {
			result.Expired++
			continue
		}
		if firstExitIdx >= len(bars) {
			result.Expired++
			continue
		}
		if hasRecentEntryGap(bars, entryIdx, timeframe, cfg.MaxEntryGapBars, cfg.CleanBarsAfterGap) ||
			hasOversizedBarGap(bars, firstExitIdx, timeframe, cfg.MaxEntryGapBars) {
			continue
		}
		sigBar := bars[s.Index]
		entryBar := bars[entryIdx]
		if !isValidBar(sigBar) || !isValidBar(entryBar) {
			continue
		}
		entry, stop, target, risk, ok := tradePlan(bars, s, entryIdx, fillMode, cfg)
		if !ok {
			continue
		}
		riskTicks := risk / cfg.TickSize
		if cfg.MinRiskTicks > 0 && riskTicks < cfg.MinRiskTicks {
			continue
		}
		if cfg.MaxRiskTicks > 0 && riskTicks > cfg.MaxRiskTicks {
			continue
		}
		if profile.DelayBars > 0 && profile.MaxChaseR > 0 {
			baseIdx, _ := entryAndFirstExitIndex(s.Index, 0, fillMode)
			if baseIdx >= len(bars) {
				result.Expired++
				continue
			}
			baseEntry, _, _, baseRisk, baseOK := tradePlan(bars, s, baseIdx, fillMode, cfg)
			chase := float64(s.Dir) * (entry - baseEntry)
			if baseOK && baseRisk > 0 && chase > profile.MaxChaseR*baseRisk {
				result.ChaseSkipped++
				continue
			}
		}

		lastIdx := entryIdx + cfg.MaxHold
		if fillMode == "next_bar_open" {
			lastIdx = entryIdx + cfg.MaxHold - 1
		}
		if lastIdx >= len(bars) {
			lastIdx = len(bars) - 1
		}
		if lastIdx < firstExitIdx || !validBarWindow(bars, firstExitIdx, lastIdx) {
			continue
		}
		tr := trade{
			Instrument:      instrument,
			Timeframe:       timeframe,
			Variant:         variant,
			SignalTime:      sigBar.Time,
			EntryTime:       entryBar.Time,
			Dir:             s.Dir,
			Reason:          s.Reason,
			Level:           s.Level,
			Entry:           entry,
			Stop:            stop,
			Target:          target,
			RiskPoints:      risk,
			Delta:           s.Delta,
			DeltaPct:        s.DeltaPct,
			DepthImb:        s.DepthImb,
			WickRatio:       s.WickRatio,
			VolumeRatio:     s.VolumeRatio,
			SignalVolume:    sigBar.Volume,
			BidVolume:       sigBar.BidVolume,
			AskVolume:       sigBar.AskVolume,
			DepthBid:        sigBar.DepthBid,
			DepthAsk:        sigBar.DepthAsk,
			TopBid:          sigBar.TopBid,
			TopAsk:          sigBar.TopAsk,
			QuoteBid:        sigBar.QuoteBid,
			QuoteAsk:        sigBar.QuoteAsk,
			BidQuotes:       sigBar.BidQuotes,
			AskQuotes:       sigBar.AskQuotes,
			SignalTrades:    sigBar.Trades,
			SignalDepthRows: sigBar.DepthRows,
		}

		var mfe, mae float64
		exitIdx := lastIdx
		exit := bars[lastIdx].Close - float64(s.Dir)*slippage
		outcome := "timeout"
		for j := firstExitIdx; j <= lastIdx; j++ {
			fav, adv := favorableAdverse(bars[j], s.Dir, entry)
			if fav > mfe {
				mfe = fav
			}
			if adv < mae {
				mae = adv
			}
			stopHit, targetHit := hitStopTarget(bars[j], s.Dir, stop, target)
			if stopHit && targetHit {
				exitIdx = j
				exit = stop - float64(s.Dir)*slippage
				outcome = "stop_same_bar"
				break
			}
			if stopHit {
				exitIdx = j
				exit = stop - float64(s.Dir)*slippage
				outcome = "stop"
				break
			}
			if targetHit {
				exitIdx = j
				exit = target
				outcome = "target"
				break
			}
		}
		points := float64(s.Dir)*(exit-entry) - costPoints
		tr.ExitTime = bars[exitIdx].Time
		tr.Exit = exit
		tr.Outcome = outcome
		tr.R = points / risk
		tr.MFER = mfe / risk
		tr.MAER = mae / risk
		result.Trades = append(result.Trades, tr)
	}
	return result
}

func validBarWindow(bars []bar, start, end int) bool {
	if start < 0 || end >= len(bars) || start > end {
		return false
	}
	for i := start; i <= end; i++ {
		if !isValidBar(bars[i]) {
			return false
		}
	}
	return true
}

func tradePlan(bars []bar, s signal, entryIdx int, fillMode string, cfg analysisConfig) (entry, stop, target, risk float64, ok bool) {
	if entryIdx >= len(bars) || s.Index < 0 || s.Index >= len(bars) {
		return 0, 0, 0, 0, false
	}
	entryBar := bars[entryIdx]
	if fillMode == "next_bar_open" {
		entry = entryBar.Open + float64(s.Dir)*cfg.SlippageTicks*cfg.TickSize
	} else {
		entry = entryBar.Close
	}
	if s.StopATR > 0 {
		risk = s.StopATR
		if s.Dir > 0 {
			stop = entry - risk
			target = entry + cfg.RR*risk
		} else {
			stop = entry + risk
			target = entry - cfg.RR*risk
		}
	} else {
		sigBar := bars[s.Index]
		buffer := cfg.StopBufferTicks * cfg.TickSize
		if s.Dir > 0 {
			stop = sigBar.Low - buffer
			risk = entry - stop
			target = entry + cfg.RR*risk
		} else {
			stop = sigBar.High + buffer
			risk = stop - entry
			target = entry - cfg.RR*risk
		}
	}
	if risk <= cfg.TickSize/2 {
		return 0, 0, 0, 0, false
	}
	return entry, stop, target, risk, true
}

func entryAndFirstExitIndex(signalIdx, delayBars int, fillMode string) (entryIdx, firstExitIdx int) {
	if delayBars < 0 {
		delayBars = 0
	}
	if normalizeFillMode(fillMode) == "next_bar_open" {
		entryIdx = signalIdx + 1 + delayBars
		return entryIdx, entryIdx
	}
	entryIdx = signalIdx + delayBars
	return entryIdx, entryIdx + 1
}

func normalizeFillMode(mode string) string {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "next", "next_bar", "next_open", "next_bar_open", "old":
		return "next_bar_open"
	case "ninja", "ninja_close", "onbarclose", "on_bar_close", "close", "":
		return "ninja_close"
	default:
		return "ninja_close"
	}
}

func fillModeDescription(mode string) string {
	if normalizeFillMode(mode) == "next_bar_open" {
		return "Entry uses the next bar open, preserving the older research fill model."
	}
	return "Entry uses the signal bar close to approximate NinjaTrader Calculate.OnBarClose market submission; stop/target evaluation starts on the following bar."
}

func hasRecentEntryGap(bars []bar, idx, timeframe, maxGapBars, cleanBarsAfterGap int) bool {
	if maxGapBars <= 0 || idx <= 0 {
		return false
	}
	start := idx
	if cleanBarsAfterGap > 0 {
		start = idx - cleanBarsAfterGap + 1
	}
	if start < 1 {
		start = 1
	}
	for i := start; i <= idx; i++ {
		if hasOversizedBarGap(bars, i, timeframe, maxGapBars) {
			return true
		}
	}
	return false
}

func hasOversizedBarGap(bars []bar, idx, timeframe, maxGapBars int) bool {
	if maxGapBars <= 0 || timeframe <= 0 || idx <= 0 || idx >= len(bars) {
		return false
	}
	maxGap := time.Duration(timeframe*maxGapBars) * time.Minute
	return bars[idx].Time.Sub(bars[idx-1].Time) > maxGap
}

func deterministicSignalPercent(s signal, variant string, timeframe int) float64 {
	h := fnv.New64a()
	_, _ = fmt.Fprintf(h, "%s|%d|%d|%d|%s|%.6f", variant, timeframe, s.Index, s.Dir, s.Reason, s.Level)
	return float64(h.Sum64()%1000000) / 1000000.0
}

func favorableAdverse(b bar, dir int, entry float64) (float64, float64) {
	if dir > 0 {
		return b.High - entry, b.Low - entry
	}
	return entry - b.Low, entry - b.High
}

func hitStopTarget(b bar, dir int, stop, target float64) (bool, bool) {
	if dir > 0 {
		return b.Low <= stop, b.High >= target
	}
	return b.High >= stop, b.Low <= target
}

func summarizeTrades(trades []trade) simSummary {
	var s simSummary
	var wins, losses float64
	var equity, peak float64
	for _, tr := range trades {
		s.Trades++
		s.TotalR += tr.R
		s.AvgRiskPoints += tr.RiskPoints
		s.AvgMFER += tr.MFER
		s.AvgMAER += tr.MAER
		switch tr.Outcome {
		case "target":
			s.Targets++
		case "stop", "stop_same_bar":
			s.Stops++
		default:
			s.Timeouts++
		}
		if tr.R > 0 {
			s.Wins++
			wins += tr.R
		} else if tr.R < 0 {
			s.Losses++
			losses += -tr.R
		}
		equity += tr.R
		if equity > peak {
			peak = equity
		}
		dd := peak - equity
		if dd > s.MaxDrawdownR {
			s.MaxDrawdownR = dd
		}
	}
	if s.Trades > 0 {
		n := float64(s.Trades)
		s.AvgR = s.TotalR / n
		s.AvgRiskPoints /= n
		s.AvgMFER /= n
		s.AvgMAER /= n
	}
	if losses > 0 {
		s.ProfitFactor = wins / losses
	} else if wins > 0 {
		s.ProfitFactor = math.Inf(1)
	}
	return s
}

type breakdownKey struct {
	Timeframe int
	Variant   string
	Bucket    string
}

type riskBudgetKey struct {
	Timeframe int
	Variant   string
}

func appendRiskBudgetAssessment(lines []string, trades []trade, budgets []float64, pointValue, stopExitSlippagePoints, costPoints float64) []string {
	lines = append(lines, "", "## Risk Budget Assessment", "")
	if pointValue <= 0 {
		lines = append(lines, "Skipped because point value is unknown for this instrument.")
		return lines
	}
	if len(budgets) == 0 {
		lines = append(lines, "No risk budgets configured.")
		return lines
	}
	if len(trades) == 0 {
		lines = append(lines, "No trades.")
		return lines
	}

	sortedBudgets := append([]float64(nil), budgets...)
	sort.Float64s(sortedBudgets)

	lines = append(lines, "Budgets are maximum planned stop-loss dollars per trade, not notional order size. Contract count is rounded down to whole futures contracts; rows with `Skipped` could not fit even one contract inside that budget.")
	lines = append(lines, "")

	grouped := make(map[riskBudgetKey][]trade)
	keys := make([]riskBudgetKey, 0)
	seen := make(map[riskBudgetKey]bool)
	for _, tr := range trades {
		key := riskBudgetKey{Timeframe: tr.Timeframe, Variant: tr.Variant}
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
		return a.Variant < b.Variant
	})

	lines = append(lines, "| TF | Variant | Budget | Tradable | Skipped | Win rate | Net $ | Max DD $ | PF | Avg contracts | Max contracts | Avg stop-risk used |")
	lines = append(lines, "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
	for _, key := range keys {
		for _, budget := range sortedBudgets {
			s := summarizeRiskBudget(grouped[key], budget, pointValue, stopExitSlippagePoints, costPoints)
			lines = append(lines, fmt.Sprintf("| %dm | %s | %s | %d | %d | %.1f%% | %s | %s | %s | %.2f | %d | %s |",
				key.Timeframe,
				key.Variant,
				formatMoney(budget),
				s.Trades,
				s.Skipped,
				riskBudgetWinRate(s),
				formatMoney(s.TotalNet),
				formatMoney(s.MaxDrawdown),
				formatPF(s.ProfitFactor),
				s.AvgContracts,
				s.MaxContracts,
				formatMoney(s.AvgStopRiskUsed)))
		}
	}
	return lines
}

func summarizeRiskBudget(trades []trade, budget, pointValue, stopExitSlippagePoints, costPoints float64) riskBudgetSummary {
	s := riskBudgetSummary{Budget: budget}
	if budget <= 0 || pointValue <= 0 {
		s.Skipped = len(trades)
		return s
	}

	var wins, losses float64
	var equity, peak float64
	for _, tr := range trades {
		stopRiskPerContract := (tr.RiskPoints + stopExitSlippagePoints + costPoints) * pointValue
		if stopRiskPerContract <= 0 {
			s.Skipped++
			continue
		}
		contracts := int(math.Floor(budget / stopRiskPerContract))
		if contracts < 1 {
			s.Skipped++
			continue
		}

		pnlPerContract := tr.R * tr.RiskPoints * pointValue
		net := pnlPerContract * float64(contracts)

		s.Trades++
		s.TotalNet += net
		s.TotalContracts += contracts
		s.AvgStopRiskUsed += stopRiskPerContract * float64(contracts)
		if contracts > s.MaxContracts {
			s.MaxContracts = contracts
		}
		switch tr.Outcome {
		case "target":
			s.Targets++
		case "stop", "stop_same_bar":
			s.Stops++
		default:
			s.Timeouts++
		}
		if net > 0 {
			s.Wins++
			wins += net
		} else if net < 0 {
			s.Losses++
			losses += -net
		}
		equity += net
		if equity > peak {
			peak = equity
		}
		dd := peak - equity
		if dd > s.MaxDrawdown {
			s.MaxDrawdown = dd
		}
	}
	if s.Trades > 0 {
		n := float64(s.Trades)
		s.AvgNet = s.TotalNet / n
		s.AvgContracts = float64(s.TotalContracts) / n
		s.AvgStopRiskUsed /= n
	}
	if losses > 0 {
		s.ProfitFactor = wins / losses
	} else if wins > 0 {
		s.ProfitFactor = math.Inf(1)
	}
	return s
}

func appendApexAccountSimulation(lines []string, trades []trade, pointValue, costPoints float64, cfg analysisConfig) []string {
	lines = append(lines, "", "## Apex 25K Fixed-Contract Simulation", "")
	if pointValue <= 0 {
		lines = append(lines, "Skipped because point value is unknown for this instrument.")
		return lines
	}
	if cfg.ApexMaxContracts <= 0 {
		lines = append(lines, "Skipped because Apex max contracts is not positive.")
		return lines
	}
	if len(trades) == 0 {
		lines = append(lines, "No trades.")
		return lines
	}

	lines = append(lines, fmt.Sprintf("Account model: start %s, target +%s, EOD drawdown %s, daily loss limit %s, max contracts %d. Daily loss pauses new trades until the next futures trading day. Threshold and daily-loss checks include intratrade adverse excursion from bar highs/lows; stop trades are capped at the modeled stop/slippage fill.",
		formatMoney(cfg.ApexStartBalance),
		formatMoney(cfg.ApexProfitTarget),
		formatMoney(cfg.ApexMaxDrawdown),
		formatMoney(cfg.ApexDailyLoss),
		cfg.ApexMaxContracts))
	lines = append(lines, "")

	grouped := make(map[riskBudgetKey][]trade)
	keys := make([]riskBudgetKey, 0)
	seen := make(map[riskBudgetKey]bool)
	for _, tr := range trades {
		key := riskBudgetKey{Timeframe: tr.Timeframe, Variant: tr.Variant}
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
		return a.Variant < b.Variant
	})

	lines = append(lines, "| TF | Variant | Contracts | Trades | DLL skipped | Net $ | End balance | High balance | Low balance | Max DD $ | Active threshold | Status | Event time |")
	lines = append(lines, "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
	for _, key := range keys {
		group := append([]trade(nil), grouped[key]...)
		sort.SliceStable(group, func(i, j int) bool {
			return group[i].EntryTime.Before(group[j].EntryTime)
		})
		for contracts := 1; contracts <= cfg.ApexMaxContracts; contracts++ {
			s := simulateApexAccount(group, contracts, pointValue, costPoints, cfg)
			lines = append(lines, fmt.Sprintf("| %dm | %s | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s |",
				key.Timeframe,
				key.Variant,
				contracts,
				s.TradesTaken,
				s.DLLSkipped,
				formatMoney(s.NetPnL),
				formatMoney(s.EndBalance),
				formatMoney(s.HighBalance),
				formatMoney(s.LowBalance),
				formatMoney(s.MaxDrawdown),
				formatMoney(s.ActiveThreshold),
				s.Status,
				formatEventTime(s)))
		}
	}
	return lines
}

func buildAdvisorRows(instrument string, bars []bar, sigs []signal, variant string, timeframe int, cfg analysisConfig, costPoints float64) []advisorRow {
	var rows []advisorRow
	for _, delayBars := range cfg.AdvisorDelays {
		for _, missRate := range cfg.AdvisorMissRates {
			profile := advisorProfile{
				Name:       advisorProfileName(delayBars, missRate, cfg.AdvisorExpiryBars, cfg.AdvisorMaxChaseR),
				DelayBars:  delayBars,
				MissRate:   missRate,
				ExpiryBars: cfg.AdvisorExpiryBars,
				MaxChaseR:  cfg.AdvisorMaxChaseR,
			}
			result := simulateTradesWithProfile(instrument, bars, sigs, variant, timeframe, cfg, costPoints, profile)
			rows = append(rows, advisorRow{
				Timeframe:    timeframe,
				Variant:      variant,
				Profile:      profile,
				Signals:      result.Signals,
				Missed:       result.Missed,
				Expired:      result.Expired,
				ChaseSkipped: result.ChaseSkipped,
				Summary:      summarizeTrades(result.Trades),
			})
		}
	}
	return rows
}

func advisorProfileName(delayBars int, missRate float64, expiryBars int, maxChaseR float64) string {
	return fmt.Sprintf("delay_%db_miss_%02.0fpct_exp_%db_chase_%.2fR", delayBars, missRate*100, expiryBars, maxChaseR)
}

func appendAdvisorSensitivity(lines []string, rows []advisorRow, cfg analysisConfig) []string {
	lines = append(lines, "", "## Advisor Confirmation Sensitivity", "")
	if len(rows) == 0 {
		lines = append(lines, "No advisor sensitivity rows.")
		return lines
	}
	lines = append(lines, "This models a human-supervised signal workflow: the strategy alerts, a human may miss some signals, and accepted signals enter after a configured bar delay. It is a research model for manual confirmation viability, not a way to disguise automation.")
	lines = append(lines, "")
	lines = append(lines, fmt.Sprintf("Delay is measured in the analyzed timeframe's bars, so `delay=1` means about 1 minute on 1m, 5 minutes on 5m, and 15 minutes on 15m. Signals expire after %d delayed bars. Max chase skips entries that moved more than %.2fR in the signal direction before the manual entry.", cfg.AdvisorExpiryBars, cfg.AdvisorMaxChaseR))
	lines = append(lines, "")

	sort.Slice(rows, func(i, j int) bool {
		a, b := rows[i], rows[j]
		if a.Timeframe != b.Timeframe {
			return a.Timeframe < b.Timeframe
		}
		if variantRank(a.Variant) != variantRank(b.Variant) {
			return variantRank(a.Variant) < variantRank(b.Variant)
		}
		if a.Variant != b.Variant {
			return a.Variant < b.Variant
		}
		if a.Profile.DelayBars != b.Profile.DelayBars {
			return a.Profile.DelayBars < b.Profile.DelayBars
		}
		return a.Profile.MissRate < b.Profile.MissRate
	})

	lines = append(lines, "| TF | Variant | Delay bars | Miss rate | Signals | Trades | Missed | Expired | Chase skipped | Win rate | Avg R | Total R | PF | Max DD R | Target | Stop | Timeout |")
	lines = append(lines, "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
	for _, row := range rows {
		s := row.Summary
		lines = append(lines, fmt.Sprintf("| %dm | %s | %d | %.0f%% | %d | %d | %d | %d | %d | %.1f%% | %.3f | %.3f | %s | %.3f | %d | %d | %d |",
			row.Timeframe,
			row.Variant,
			row.Profile.DelayBars,
			row.Profile.MissRate*100,
			row.Signals,
			s.Trades,
			row.Missed,
			row.Expired,
			row.ChaseSkipped,
			summaryWinRate(s),
			s.AvgR,
			s.TotalR,
			formatPF(s.ProfitFactor),
			s.MaxDrawdownR,
			s.Targets,
			s.Stops,
			s.Timeouts))
	}
	return lines
}
