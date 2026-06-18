package main

import (
	"math"
	"sort"
	"time"
)

func resample(in []bar, minutes int) []bar {
	if minutes <= 1 {
		return in
	}
	loc := in[0].Time.Location()
	buckets := make(map[int64]*bar, len(in)/minutes+1)
	var keys []int64
	dur := int64(time.Duration(minutes) * time.Minute)
	for _, x := range in {
		if !isValidBar(x) {
			continue
		}
		k := x.Time.UnixNano() / dur * dur
		b := buckets[k]
		if b == nil {
			t := time.Unix(0, k).In(loc)
			b = &bar{Time: t, Open: x.Open, High: x.High, Low: x.Low, Close: x.Close}
			buckets[k] = b
			keys = append(keys, k)
		}
		if x.High > b.High {
			b.High = x.High
		}
		if x.Low < b.Low || b.Low == 0 {
			b.Low = x.Low
		}
		b.Close = x.Close
		b.Volume += x.Volume
		b.BidVolume += x.BidVolume
		b.AskVolume += x.AskVolume
		b.Trades += x.Trades
		b.QuoteRows += x.QuoteRows
		b.DepthRows += x.DepthRows
		b.UnknownVol += x.UnknownVol
		b.DepthBid += x.DepthBid
		b.DepthAsk += x.DepthAsk
		b.TopBid += x.TopBid
		b.TopAsk += x.TopAsk
		b.QuoteBid += x.QuoteBid
		b.QuoteAsk += x.QuoteAsk
		b.BidQuotes += x.BidQuotes
		b.AskQuotes += x.AskQuotes
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	out := make([]bar, 0, len(keys))
	for _, k := range keys {
		if isValidBar(*buckets[k]) {
			out = append(out, *buckets[k])
		}
	}
	return out
}

func detectSignals(bars []bar, lookback int, minWick, minVolRatio, minDepthImb float64, requireVol, requireDelta, requireDepth bool) []signal {
	var sigs []signal
	for i := lookback; i < len(bars)-1; i++ {
		prevHigh := bars[i-lookback].High
		prevLow := bars[i-lookback].Low
		var avgVol float64
		for j := i - lookback; j < i; j++ {
			if bars[j].High > prevHigh {
				prevHigh = bars[j].High
			}
			if bars[j].Low < prevLow {
				prevLow = bars[j].Low
			}
			avgVol += float64(bars[j].Volume)
		}
		avgVol /= float64(lookback)
		if avgVol <= 0 {
			avgVol = 1
		}
		x := bars[i]
		rng := x.High - x.Low
		if rng <= 0 {
			continue
		}
		delta := x.AskVolume - x.BidVolume
		tradeVol := x.AskVolume + x.BidVolume
		deltaPct := 0.0
		if tradeVol > 0 {
			deltaPct = float64(delta) / float64(tradeVol)
		}
		depthImb := 0.0
		depthTotal := x.TopBid + x.TopAsk
		if depthTotal > 0 {
			depthImb = float64(x.TopBid-x.TopAsk) / float64(depthTotal)
		} else {
			quoteTotal := x.QuoteBid + x.QuoteAsk
			if quoteTotal > 0 {
				depthImb = float64(x.QuoteBid-x.QuoteAsk) / float64(quoteTotal)
			}
		}
		volRatio := float64(x.Volume) / avgVol
		if requireVol && volRatio < minVolRatio {
			continue
		}

		if x.High > prevHigh && x.Close < prevHigh {
			wick := (x.High - math.Max(x.Open, x.Close)) / rng
			if wick >= minWick &&
				(!requireDelta || deltaPct > 0.10) &&
				(!requireDepth || depthImb <= -minDepthImb) {
				sigs = append(sigs, signal{i, -1, "bearish_high_sweep", prevHigh, delta, deltaPct, depthImb, wick, volRatio, 0})
			}
		}
		if x.Low < prevLow && x.Close > prevLow {
			wick := (math.Min(x.Open, x.Close) - x.Low) / rng
			if wick >= minWick &&
				(!requireDelta || deltaPct < -0.10) &&
				(!requireDepth || depthImb >= minDepthImb) {
				sigs = append(sigs, signal{i, 1, "bullish_low_sweep", prevLow, delta, deltaPct, depthImb, wick, volRatio, 0})
			}
		}
	}
	return sigs
}

func detectMACDSignals(bars []bar, fast, slow, signalPeriod, volumeLookback int, requireZeroTrend bool) []signal {
	if fast <= 0 || slow <= fast || signalPeriod <= 0 || len(bars) < slow+signalPeriod+2 {
		return nil
	}

	closes := make([]float64, len(bars))
	for i, b := range bars {
		closes[i] = b.Close
	}
	fastEMA := emaSeries(closes, fast)
	slowEMA := emaSeries(closes, slow)
	macdLine := make([]float64, len(bars))
	for i := range macdLine {
		macdLine[i] = fastEMA[i] - slowEMA[i]
	}
	signalLine := emaSeries(macdLine, signalPeriod)

	warmup := slow + signalPeriod
	if volumeLookback > warmup {
		warmup = volumeLookback
	}
	if warmup < 1 {
		warmup = 1
	}

	var sigs []signal
	for i := warmup; i < len(bars)-1; i++ {
		prevDiff := macdLine[i-1] - signalLine[i-1]
		diff := macdLine[i] - signalLine[i]
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)

		if prevDiff <= 0 && diff > 0 {
			if requireZeroTrend && macdLine[i] <= 0 {
				continue
			}
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "macd_bull_cross",
				Level:       bars[i].Close,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				WickRatio:   0,
				VolumeRatio: volRatio,
			})
		}
		if prevDiff >= 0 && diff < 0 {
			if requireZeroTrend && macdLine[i] >= 0 {
				continue
			}
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "macd_bear_cross",
				Level:       bars[i].Close,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				WickRatio:   0,
				VolumeRatio: volRatio,
			})
		}
	}
	return sigs
}

func emaSeries(values []float64, period int) []float64 {
	out := make([]float64, len(values))
	if len(values) == 0 || period <= 0 {
		return out
	}
	alpha := 2.0 / float64(period+1)
	out[0] = values[0]
	for i := 1; i < len(values); i++ {
		out[i] = alpha*values[i] + (1-alpha)*out[i-1]
	}
	return out
}

func signalBarMetrics(bars []bar, i, volumeLookback int) (int64, float64, float64, float64) {
	x := bars[i]
	delta := x.AskVolume - x.BidVolume
	tradeVol := x.AskVolume + x.BidVolume
	deltaPct := 0.0
	if tradeVol > 0 {
		deltaPct = float64(delta) / float64(tradeVol)
	}

	depthImb := 0.0
	depthTotal := x.TopBid + x.TopAsk
	if depthTotal > 0 {
		depthImb = float64(x.TopBid-x.TopAsk) / float64(depthTotal)
	} else {
		quoteTotal := x.QuoteBid + x.QuoteAsk
		if quoteTotal > 0 {
			depthImb = float64(x.QuoteBid-x.QuoteAsk) / float64(quoteTotal)
		}
	}

	volRatio := 0.0
	if volumeLookback > 0 && i >= volumeLookback {
		var avgVol float64
		for j := i - volumeLookback; j < i; j++ {
			avgVol += float64(bars[j].Volume)
		}
		avgVol /= float64(volumeLookback)
		if avgVol > 0 {
			volRatio = float64(x.Volume) / avgVol
		}
	}

	return delta, deltaPct, depthImb, volRatio
}

func detectDonchianBreakoutSignals(bars []bar, lookback, volumeLookback int, minVolRatio, minDepthImb float64, requireVol, requireDelta, requireDepth bool) []signal {
	if lookback <= 0 || len(bars) < lookback+2 {
		return nil
	}
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := lookback; i < len(bars)-1; i++ {
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
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if bars[i].Close > prevHigh && passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, requireDepth) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "donchian_close_above_range",
				Level:       prevHigh,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i] * 1.1,
			})
		}
		if bars[i].Close < prevLow && passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, requireDepth) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "donchian_close_below_range",
				Level:       prevLow,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i] * 1.1,
			})
		}
	}
	return sigs
}

func detectBollingerBreakoutSignals(bars []bar, period, volumeLookback int, minVolRatio, minDepthImb float64, requireVol, requireDelta, requireDepth bool) []signal {
	if period <= 1 || len(bars) < period+2 {
		return nil
	}
	closes := make([]float64, len(bars))
	for i := range bars {
		closes[i] = bars[i].Close
	}
	mean := smaSeries(closes, period)
	std := stdSeries(closes, period)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := period - 1; i < len(bars)-1; i++ {
		if std[i] <= 0 {
			continue
		}
		upper := mean[i] + 2*std[i]
		lower := mean[i] - 2*std[i]
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if bars[i].Close > upper && passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, requireDepth) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "bollinger_close_above_upper",
				Level:       upper,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i] * 1.1,
			})
		}
		if bars[i].Close < lower && passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, requireDepth) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "bollinger_close_below_lower",
				Level:       lower,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i] * 1.1,
			})
		}
	}
	return sigs
}

func detectRSIReversionSignals(bars []bar, period, volumeLookback int) []signal {
	if period <= 1 || len(bars) < period+2 {
		return nil
	}
	closes := make([]float64, len(bars))
	for i := range bars {
		closes[i] = bars[i].Close
	}
	rsi := rsiSeries(closes, period)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := period + 1; i < len(bars)-1; i++ {
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if rsi[i-1] <= 30 && rsi[i] > 30 {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "rsi_cross_back_above_30",
				Level:       rsi[i],
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i],
			})
		}
		if rsi[i-1] >= 70 && rsi[i] < 70 {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "rsi_cross_back_below_70",
				Level:       rsi[i],
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i],
			})
		}
	}
	return sigs
}

func detectDepthDeltaMomentumSignals(bars []bar, volumeLookback int, minVolRatio, minDepthImb float64) []signal {
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 14; i < len(bars)-1; i++ {
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if volRatio < minVolRatio {
			continue
		}
		if bars[i].Close > bars[i].Open && deltaPct >= 0.20 && depthImb >= minDepthImb {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "depth_delta_bull_momentum",
				Level:       bars[i].Close,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i] * 0.9,
			})
		}
		if bars[i].Close < bars[i].Open && deltaPct <= -0.20 && depthImb <= -minDepthImb {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "depth_delta_bear_momentum",
				Level:       bars[i].Close,
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
				StopATR:     atrs[i] * 0.9,
			})
		}
	}
	return sigs
}

func detectVWAPReclaimSignals(bars []bar, volumeLookback int, minVolRatio, minDepthImb float64, requireVol, requireDelta bool) []signal {
	if len(bars) < 16 {
		return nil
	}
	vwaps := sessionVWAPSeries(bars)
	var sigs []signal
	for i := 15; i < len(bars)-1; i++ {
		if vwaps[i] <= 0 || vwaps[i-1] <= 0 {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if bars[i-1].Close <= vwaps[i-1] && bars[i].Close > vwaps[i] && bars[i].Close > bars[i].Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "vwap_bull_reclaim",
				Level:       vwaps[i],
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
			})
		}
		if bars[i-1].Close >= vwaps[i-1] && bars[i].Close < vwaps[i] && bars[i].Close < bars[i].Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "vwap_bear_reclaim",
				Level:       vwaps[i],
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
			})
		}
	}
	return sigs
}

func detectVWAPRejectionSignals(bars []bar, volumeLookback int, minVolRatio, minDepthImb float64, requireVol, requireDelta bool) []signal {
	if len(bars) < 16 {
		return nil
	}
	vwaps := sessionVWAPSeries(bars)
	atr := atrSeries(bars, 14)
	var sigs []signal
	for i := 15; i < len(bars)-1; i++ {
		if vwaps[i] <= 0 || vwaps[i-1] <= 0 || atr[i] <= 0 {
			continue
		}
		tolerance := 0.25 * atr[i]
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if bars[i-1].Close > vwaps[i-1] && bars[i].Low <= vwaps[i]+tolerance && bars[i].Close > vwaps[i] && bars[i].Close > bars[i].Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         1,
				Reason:      "vwap_bull_rejection",
				Level:       vwaps[i],
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
			})
		}
		if bars[i-1].Close < vwaps[i-1] && bars[i].High >= vwaps[i]-tolerance && bars[i].Close < vwaps[i] && bars[i].Close < bars[i].Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
			sigs = append(sigs, signal{
				Index:       i,
				Dir:         -1,
				Reason:      "vwap_bear_rejection",
				Level:       vwaps[i],
				Delta:       delta,
				DeltaPct:    deltaPct,
				DepthImb:    depthImb,
				VolumeRatio: volRatio,
			})
		}
	}
	return sigs
}

func sessionVWAPSeries(bars []bar) []float64 {
	out := make([]float64, len(bars))
	var day string
	var pv, vol float64
	for i, b := range bars {
		d := tradingDay(b.Time)
		if d != day {
			day = d
			pv = 0
			vol = 0
		}
		barVol := float64(b.Volume)
		if barVol <= 0 {
			barVol = 1
		}
		typical := (b.High + b.Low + b.Close) / 3
		pv += typical * barVol
		vol += barVol
		if vol > 0 {
			out[i] = pv / vol
		}
	}
	return out
}

func detectOpeningRangeSignals(bars []bar, rangeMinutes, volumeLookback int, minVolRatio, minDepthImb float64, retest, requireVol, requireDelta bool) []signal {
	if rangeMinutes <= 0 || len(bars) < 3 {
		return nil
	}
	const rthOpen = 9*60 + 30
	rangeEnd := rthOpen + rangeMinutes
	type orState struct {
		Day          string
		High         float64
		Low          float64
		Ready        bool
		LongBreak    bool
		ShortBreak   bool
		LongSignaled bool
		ShortSignal  bool
	}
	var state orState
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 0; i < len(bars)-1; i++ {
		b := bars[i]
		day := tradingDay(b.Time)
		if day != state.Day {
			state = orState{Day: day}
		}
		m := sessionMinute(b.Time)
		if m < rthOpen || m >= 16*60 {
			continue
		}
		if m >= rthOpen && m < rangeEnd {
			if state.High == 0 || b.High > state.High {
				state.High = b.High
			}
			if state.Low == 0 || b.Low < state.Low {
				state.Low = b.Low
			}
			continue
		}
		if m >= rangeEnd && state.High > state.Low {
			state.Ready = true
		}
		if !state.Ready {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if retest {
			if state.LongBreak && !state.LongSignaled && b.Low <= state.High && b.Close > state.High && b.Close > b.Open &&
				passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "orb_retest_high", Level: state.High, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
				state.LongSignaled = true
			}
			if state.ShortBreak && !state.ShortSignal && b.High >= state.Low && b.Close < state.Low && b.Close < b.Open &&
				passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "orb_retest_low", Level: state.Low, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
				state.ShortSignal = true
			}
			if b.Close > state.High {
				state.LongBreak = true
			}
			if b.Close < state.Low {
				state.ShortBreak = true
			}
			continue
		}
		if !state.LongSignaled && b.Close > state.High &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "orb_break_high", Level: state.High, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i] * 1.1})
			state.LongSignaled = true
		}
		if !state.ShortSignal && b.Close < state.Low &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, requireVol, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "orb_break_low", Level: state.Low, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i] * 1.1})
			state.ShortSignal = true
		}
	}
	return sigs
}

func detectOpeningDrivePullbackSignals(bars []bar, rangeMinutes, volumeLookback int, minVolRatio, minDepthImb float64, requireDelta bool) []signal {
	if rangeMinutes <= 0 || len(bars) < 3 {
		return nil
	}
	const rthOpen = 9*60 + 30
	rangeEnd := rthOpen + rangeMinutes
	type driveState struct {
		Day      string
		Open     float64
		Close    float64
		High     float64
		Low      float64
		Dir      int
		Ready    bool
		Extended bool
		Signaled bool
	}
	var state driveState
	vwaps := sessionVWAPSeries(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 0; i < len(bars)-1; i++ {
		b := bars[i]
		day := tradingDay(b.Time)
		if day != state.Day {
			state = driveState{Day: day}
		}
		m := sessionMinute(b.Time)
		if m < rthOpen || m >= 12*60 {
			continue
		}
		if m >= rthOpen && m < rangeEnd {
			if state.Open == 0 {
				state.Open = b.Open
				if state.Open == 0 {
					state.Open = b.Close
				}
				state.High = b.High
				state.Low = b.Low
			}
			if b.High > state.High {
				state.High = b.High
			}
			if b.Low < state.Low || state.Low == 0 {
				state.Low = b.Low
			}
			state.Close = b.Close
			continue
		}
		if !state.Ready && m >= rangeEnd && state.High > state.Low && state.Open > 0 && state.Close > 0 {
			rng := state.High - state.Low
			ret := state.Close - state.Open
			threshold := math.Max(0.25*rng, 0.25)
			if ret > threshold {
				state.Dir = 1
			} else if ret < -threshold {
				state.Dir = -1
			}
			state.Ready = state.Dir != 0
		}
		if !state.Ready || state.Signaled || vwaps[i] <= 0 || atrs[i] <= 0 {
			continue
		}
		tolerance := 0.25 * atrs[i]
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if state.Dir > 0 {
			if b.Close > state.High {
				state.Extended = true
			}
			heldRangeHigh := state.Extended && b.Low <= state.High+tolerance && b.Close > state.High
			heldVWAP := b.Low <= vwaps[i]+tolerance && b.Close > vwaps[i]
			if state.Extended && (heldRangeHigh || heldVWAP) && b.Close > b.Open &&
				passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "opening_drive_pullback_long", Level: math.Max(state.High, vwaps[i]), Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
				state.Signaled = true
			}
		} else {
			if b.Close < state.Low {
				state.Extended = true
			}
			heldRangeLow := state.Extended && b.High >= state.Low-tolerance && b.Close < state.Low
			heldVWAP := b.High >= vwaps[i]-tolerance && b.Close < vwaps[i]
			if state.Extended && (heldRangeLow || heldVWAP) && b.Close < b.Open &&
				passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "opening_drive_pullback_short", Level: math.Min(state.Low, vwaps[i]), Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
				state.Signaled = true
			}
		}
	}
	return sigs
}

func detectOpeningDriveFailureSignals(bars []bar, rangeMinutes, volumeLookback int, minVolRatio, minDepthImb float64, requireDelta bool) []signal {
	if rangeMinutes <= 0 || len(bars) < 3 {
		return nil
	}
	const rthOpen = 9*60 + 30
	rangeEnd := rthOpen + rangeMinutes
	type failureState struct {
		Day          string
		High         float64
		Low          float64
		Ready        bool
		HighBreak    bool
		LowBreak     bool
		HighSignaled bool
		LowSignaled  bool
	}
	var state failureState
	vwaps := sessionVWAPSeries(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 0; i < len(bars)-1; i++ {
		b := bars[i]
		day := tradingDay(b.Time)
		if day != state.Day {
			state = failureState{Day: day}
		}
		m := sessionMinute(b.Time)
		if m < rthOpen || m >= 12*60 {
			continue
		}
		if m >= rthOpen && m < rangeEnd {
			if state.High == 0 || b.High > state.High {
				state.High = b.High
			}
			if state.Low == 0 || b.Low < state.Low {
				state.Low = b.Low
			}
			continue
		}
		if m >= rangeEnd && state.High > state.Low {
			state.Ready = true
		}
		if !state.Ready || vwaps[i] <= 0 || atrs[i] <= 0 {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if b.Close > state.High {
			state.HighBreak = true
		}
		if b.Close < state.Low {
			state.LowBreak = true
		}
		if state.HighBreak && !state.HighSignaled && b.Close < state.High && b.Close < vwaps[i] && b.Close < b.Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "opening_drive_failed_high", Level: state.High, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			state.HighSignaled = true
		}
		if state.LowBreak && !state.LowSignaled && b.Close > state.Low && b.Close > vwaps[i] && b.Close > b.Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "opening_drive_failed_low", Level: state.Low, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			state.LowSignaled = true
		}
	}
	return sigs
}

func detectInitialBalanceSignals(bars []bar, rangeMinutes, volumeLookback int, minVolRatio, minDepthImb float64, acceptance, requireDelta bool) []signal {
	if rangeMinutes <= 0 || len(bars) < 3 {
		return nil
	}
	const rthOpen = 9*60 + 30
	rangeEnd := rthOpen + rangeMinutes
	type ibState struct {
		Day           string
		High          float64
		Low           float64
		Ready         bool
		AboveCloses   int
		BelowCloses   int
		LongSignaled  bool
		ShortSignaled bool
	}
	var state ibState
	vwaps := sessionVWAPSeries(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 0; i < len(bars)-1; i++ {
		b := bars[i]
		day := tradingDay(b.Time)
		if day != state.Day {
			state = ibState{Day: day}
		}
		m := sessionMinute(b.Time)
		if m < rthOpen || m >= 15*60 {
			continue
		}
		if m >= rthOpen && m < rangeEnd {
			if state.High == 0 || b.High > state.High {
				state.High = b.High
			}
			if state.Low == 0 || b.Low < state.Low {
				state.Low = b.Low
			}
			continue
		}
		if m >= rangeEnd && state.High > state.Low {
			state.Ready = true
		}
		if !state.Ready || vwaps[i] <= 0 || atrs[i] <= 0 {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if acceptance {
			if b.Close > state.High {
				state.AboveCloses++
			} else {
				state.AboveCloses = 0
			}
			if b.Close < state.Low {
				state.BelowCloses++
			} else {
				state.BelowCloses = 0
			}
			if !state.LongSignaled && state.AboveCloses >= 2 && b.Close > vwaps[i] &&
				passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "ib_acceptance_above_high", Level: state.High, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i] * 1.1})
				state.LongSignaled = true
			}
			if !state.ShortSignaled && state.BelowCloses >= 2 && b.Close < vwaps[i] &&
				passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "ib_acceptance_below_low", Level: state.Low, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i] * 1.1})
				state.ShortSignaled = true
			}
			continue
		}
		if !state.ShortSignaled && b.High > state.High && b.Close < state.High && b.Close < vwaps[i] && b.Close < b.Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "ib_reject_high", Level: state.High, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			state.ShortSignaled = true
		}
		if !state.LongSignaled && b.Low < state.Low && b.Close > state.Low && b.Close > vwaps[i] && b.Close > b.Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "ib_reject_low", Level: state.Low, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			state.LongSignaled = true
		}
	}
	return sigs
}

func detectInitialBalanceStrictAcceptanceSignals(bars []bar, rangeMinutes, volumeLookback int, minVolRatio, minDepthImb float64, requireDelta bool) []signal {
	if rangeMinutes <= 0 || len(bars) < 3 {
		return nil
	}
	const rthOpen = 9*60 + 30
	rangeEnd := rthOpen + rangeMinutes
	type ibState struct {
		Day           string
		High          float64
		Low           float64
		Ready         bool
		AboveCloses   int
		BelowCloses   int
		LongSignaled  bool
		ShortSignaled bool
	}
	var state ibState
	vwaps := sessionVWAPSeries(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 0; i < len(bars)-1; i++ {
		b := bars[i]
		day := tradingDay(b.Time)
		if day != state.Day {
			state = ibState{Day: day}
		}
		m := sessionMinute(b.Time)
		if m < rthOpen || m >= 15*60 {
			continue
		}
		if m >= rthOpen && m < rangeEnd {
			if state.High == 0 || b.High > state.High {
				state.High = b.High
			}
			if state.Low == 0 || b.Low < state.Low {
				state.Low = b.Low
			}
			continue
		}
		if m >= rangeEnd && state.High > state.Low {
			state.Ready = true
		}
		if !state.Ready || vwaps[i] <= 0 || atrs[i] <= 0 {
			continue
		}
		vwapSlope := 0.0
		if i >= 5 && vwaps[i-5] > 0 {
			vwapSlope = vwaps[i] - vwaps[i-5]
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if b.Close > state.High {
			state.AboveCloses++
		} else {
			state.AboveCloses = 0
		}
		if b.Close < state.Low {
			state.BelowCloses++
		} else {
			state.BelowCloses = 0
		}
		if !state.LongSignaled && state.AboveCloses >= 3 && b.Close > vwaps[i] && vwapSlope >= 0 &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "ib_strict_acceptance_above_high", Level: state.High, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i] * 1.1})
			state.LongSignaled = true
		}
		if !state.ShortSignaled && state.BelowCloses >= 3 && b.Close < vwaps[i] && vwapSlope <= 0 &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "ib_strict_acceptance_below_low", Level: state.Low, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i] * 1.1})
			state.ShortSignaled = true
		}
	}
	return sigs
}

func detectVWAPSlopeSignals(bars []bar, volumeLookback int, minVolRatio, minDepthImb float64, continuation, requireDelta bool) []signal {
	if len(bars) < 20 {
		return nil
	}
	vwaps := sessionVWAPSeries(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 15; i < len(bars)-1; i++ {
		if vwaps[i] <= 0 || vwaps[i-5] <= 0 || atrs[i] <= 0 {
			continue
		}
		slope := vwaps[i] - vwaps[i-5]
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		tolerance := 0.25 * atrs[i]
		if continuation {
			threshold := 0.08 * atrs[i]
			if slope > threshold && bars[i-1].Close > vwaps[i-1] && bars[i].Low <= vwaps[i]+tolerance && bars[i].Close > vwaps[i] && bars[i].Close > bars[i].Open &&
				passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "vwap_slope_bull_pullback", Level: vwaps[i], Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			}
			if slope < -threshold && bars[i-1].Close < vwaps[i-1] && bars[i].High >= vwaps[i]-tolerance && bars[i].Close < vwaps[i] && bars[i].Close < bars[i].Open &&
				passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "vwap_slope_bear_pullback", Level: vwaps[i], Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			}
			continue
		}
		flatThreshold := 0.04 * atrs[i]
		if math.Abs(slope) > flatThreshold {
			continue
		}
		extension := 1.15 * atrs[i]
		if bars[i].Low < vwaps[i]-extension && bars[i].Close > bars[i].Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "vwap_flat_lower_reversion", Level: vwaps[i], Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
		if bars[i].High > vwaps[i]+extension && bars[i].Close < bars[i].Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "vwap_flat_upper_reversion", Level: vwaps[i], Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
	}
	return sigs
}

type sessionLevels struct {
	PriorRTHHigh  float64
	PriorRTHLow   float64
	PriorRTHClose float64
	PriorRTHVWAP  float64
	OvernightHigh float64
	OvernightLow  float64
	PriorOK       bool
	OvernightOK   bool
}

func detectSessionLevelSignals(bars []bar, levelName string, volumeLookback int, minVolRatio, minDepthImb float64, rejection, requireDelta bool) []signal {
	if len(bars) < 3 {
		return nil
	}
	levels := sessionLevelsByBar(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 1; i < len(bars)-1; i++ {
		level, ok := sessionLevelValue(levels[i], levelName)
		if !ok || level <= 0 || atrs[i] <= 0 {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if volRatio < minVolRatio {
			continue
		}
		if rejection {
			tolerance := 0.10 * atrs[i]
			if bars[i].High >= level-tolerance && bars[i].Close < level && bars[i].Close < bars[i].Open &&
				passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: -1, Reason: levelName + "_bear_rejection", Level: level, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			}
			if bars[i].Low <= level+tolerance && bars[i].Close > level && bars[i].Close > bars[i].Open &&
				passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
				sigs = append(sigs, signal{Index: i, Dir: 1, Reason: levelName + "_bull_rejection", Level: level, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
			}
			continue
		}
		if bars[i-1].Close <= level && bars[i].Close > level && bars[i].Close > bars[i].Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: levelName + "_bull_reclaim", Level: level, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
		if bars[i-1].Close >= level && bars[i].Close < level && bars[i].Close < bars[i].Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: levelName + "_bear_reclaim", Level: level, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
	}
	return sigs
}

func sessionLevelValue(l sessionLevels, name string) (float64, bool) {
	switch name {
	case "prior_rth_high":
		return l.PriorRTHHigh, l.PriorOK
	case "prior_rth_low":
		return l.PriorRTHLow, l.PriorOK
	case "prior_rth_close":
		return l.PriorRTHClose, l.PriorOK
	case "prior_rth_vwap":
		return l.PriorRTHVWAP, l.PriorOK
	case "overnight_high":
		return l.OvernightHigh, l.OvernightOK
	case "overnight_low":
		return l.OvernightLow, l.OvernightOK
	default:
		return 0, false
	}
}

func sessionLevelsByBar(bars []bar) []sessionLevels {
	out := make([]sessionLevels, len(bars))
	if len(bars) == 0 {
		return out
	}
	type rthSummary struct {
		High  float64
		Low   float64
		Close float64
		VWAP  float64
		OK    bool
	}
	type overnightSummary struct {
		High float64
		Low  float64
		OK   bool
	}
	dayOrder := make([]string, 0)
	dayBars := make(map[string][]bar)
	seen := make(map[string]bool)
	for _, b := range bars {
		day := tradingDay(b.Time)
		if !seen[day] {
			seen[day] = true
			dayOrder = append(dayOrder, day)
		}
		dayBars[day] = append(dayBars[day], b)
	}
	sort.Strings(dayOrder)
	rthByDay := make(map[string]rthSummary)
	overnightByDay := make(map[string]overnightSummary)
	for _, day := range dayOrder {
		var r rthSummary
		var o overnightSummary
		var pv, vol float64
		for _, b := range dayBars[day] {
			if inRTH(b.Time) {
				if r.High == 0 || b.High > r.High {
					r.High = b.High
				}
				if r.Low == 0 || b.Low < r.Low {
					r.Low = b.Low
				}
				r.Close = b.Close
				barVol := float64(b.Volume)
				if barVol <= 0 {
					barVol = 1
				}
				pv += ((b.High + b.Low + b.Close) / 3) * barVol
				vol += barVol
				r.OK = true
				continue
			}
			if sessionMinute(b.Time) < 9*60+30 {
				if o.High == 0 || b.High > o.High {
					o.High = b.High
				}
				if o.Low == 0 || b.Low < o.Low {
					o.Low = b.Low
				}
				o.OK = true
			}
		}
		if r.OK && vol > 0 {
			r.VWAP = pv / vol
		}
		rthByDay[day] = r
		overnightByDay[day] = o
	}
	priorByDay := make(map[string]rthSummary)
	for i := 1; i < len(dayOrder); i++ {
		priorByDay[dayOrder[i]] = rthByDay[dayOrder[i-1]]
	}
	for i, b := range bars {
		day := tradingDay(b.Time)
		prior := priorByDay[day]
		overnight := overnightByDay[day]
		out[i] = sessionLevels{
			PriorRTHHigh:  prior.High,
			PriorRTHLow:   prior.Low,
			PriorRTHClose: prior.Close,
			PriorRTHVWAP:  prior.VWAP,
			OvernightHigh: overnight.High,
			OvernightLow:  overnight.Low,
			PriorOK:       prior.OK,
			OvernightOK:   overnight.OK && sessionMinute(b.Time) >= 9*60+30,
		}
	}
	return out
}

type priorValueArea struct {
	POC float64
	VAH float64
	VAL float64
	OK  bool
}

func detectPriorValueReclaimSignals(bars []bar, tickSize float64, volumeLookback int, minVolRatio float64, requireDelta bool) []signal {
	if len(bars) < 3 || tickSize <= 0 {
		return nil
	}
	areas := priorValueAreasByBar(bars, tickSize)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 1; i < len(bars)-1; i++ {
		area := areas[i]
		if !area.OK {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if volRatio < minVolRatio {
			continue
		}
		if bars[i-1].Close < area.VAL && bars[i].Close > area.VAL && bars[i].Close > bars[i].Open &&
			(!requireDelta || deltaPct >= 0.05) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "value_reclaim_val", Level: area.VAL, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
		if bars[i-1].Close > area.VAH && bars[i].Close < area.VAH && bars[i].Close < bars[i].Open &&
			(!requireDelta || deltaPct <= -0.05) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "value_reclaim_vah", Level: area.VAH, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
	}
	return sigs
}

func detectVWAPAbsorptionReversalSignals(bars []bar, volumeLookback int, minVolRatio, minDepthImb float64, requireDelta bool) []signal {
	if len(bars) < 20 {
		return nil
	}
	vwaps := sessionVWAPSeries(bars)
	atrs := atrSeries(bars, 14)
	var sigs []signal
	for i := 16; i < len(bars)-1; i++ {
		prev := bars[i-1]
		b := bars[i]
		if vwaps[i-1] <= 0 || atrs[i-1] <= 0 || atrs[i] <= 0 {
			continue
		}
		prevRange := prev.High - prev.Low
		if prevRange <= 0 {
			continue
		}
		_, _, _, prevVolRatio := signalBarMetrics(bars, i-1, volumeLookback)
		bodyRatio := math.Abs(prev.Close-prev.Open) / prevRange
		if prevVolRatio < minVolRatio || bodyRatio > 0.35 {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		tolerance := 0.35 * atrs[i-1]
		if prev.Low <= vwaps[i-1]+tolerance && b.Close > prev.High && b.Close > b.Open &&
			passesOrderFlowFilters(1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "vwap_absorption_bull_reversal", Level: vwaps[i], Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
		if prev.High >= vwaps[i-1]-tolerance && b.Close < prev.Low && b.Close < b.Open &&
			passesOrderFlowFilters(-1, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb, false, requireDelta, false) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "vwap_absorption_bear_reversal", Level: vwaps[i], Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio, StopATR: atrs[i]})
		}
	}
	return sigs
}

func detectPriorValueAreaSignals(bars []bar, tickSize float64, volumeLookback int, minVolRatio float64, breakout, requireDelta bool) []signal {
	if len(bars) < 3 || tickSize <= 0 {
		return nil
	}
	areas := priorValueAreasByBar(bars, tickSize)
	var sigs []signal
	for i := 1; i < len(bars)-1; i++ {
		area := areas[i]
		if !area.OK {
			continue
		}
		delta, deltaPct, depthImb, volRatio := signalBarMetrics(bars, i, volumeLookback)
		if volRatio < minVolRatio {
			continue
		}
		if requireDelta {
			if breakout {
				if bars[i-1].Close <= area.VAH && bars[i].Close > area.VAH && deltaPct >= 0.10 {
					sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "value_break_above_vah", Level: area.VAH, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio})
				}
				if bars[i-1].Close >= area.VAL && bars[i].Close < area.VAL && deltaPct <= -0.10 {
					sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "value_break_below_val", Level: area.VAL, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio})
				}
				continue
			}
		}
		if breakout {
			if bars[i-1].Close <= area.VAH && bars[i].Close > area.VAH {
				sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "value_break_above_vah", Level: area.VAH, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio})
			}
			if bars[i-1].Close >= area.VAL && bars[i].Close < area.VAL {
				sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "value_break_below_val", Level: area.VAL, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio})
			}
			continue
		}
		if bars[i].Low <= area.VAL && bars[i].Close > area.VAL && bars[i].Close > bars[i].Open &&
			(!requireDelta || deltaPct >= 0.05) {
			sigs = append(sigs, signal{Index: i, Dir: 1, Reason: "value_reject_val", Level: area.VAL, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio})
		}
		if bars[i].High >= area.VAH && bars[i].Close < area.VAH && bars[i].Close < bars[i].Open &&
			(!requireDelta || deltaPct <= -0.05) {
			sigs = append(sigs, signal{Index: i, Dir: -1, Reason: "value_reject_vah", Level: area.VAH, Delta: delta, DeltaPct: deltaPct, DepthImb: depthImb, VolumeRatio: volRatio})
		}
	}
	return sigs
}

func priorValueAreasByBar(bars []bar, tickSize float64) []priorValueArea {
	out := make([]priorValueArea, len(bars))
	if len(bars) == 0 || tickSize <= 0 {
		return out
	}
	dayOrder := make([]string, 0)
	dayBars := make(map[string][]bar)
	seen := make(map[string]bool)
	for _, b := range bars {
		day := tradingDay(b.Time)
		if !seen[day] {
			seen[day] = true
			dayOrder = append(dayOrder, day)
		}
		dayBars[day] = append(dayBars[day], b)
	}
	areaByDay := make(map[string]priorValueArea)
	for i := 1; i < len(dayOrder); i++ {
		areaByDay[dayOrder[i]] = profileArea(dayBars[dayOrder[i-1]], tickSize)
	}
	for i, b := range bars {
		out[i] = areaByDay[tradingDay(b.Time)]
	}
	return out
}

func profileArea(bars []bar, tickSize float64) priorValueArea {
	volumes := make(map[int64]float64)
	var total float64
	for _, b := range bars {
		price := (b.High + b.Low + b.Close) / 3
		key := int64(math.Round(price / tickSize))
		vol := float64(b.Volume)
		if vol <= 0 {
			vol = 1
		}
		volumes[key] += vol
		total += vol
	}
	if total <= 0 || len(volumes) == 0 {
		return priorValueArea{}
	}
	keys := make([]int64, 0, len(volumes))
	var pocKey int64
	var pocVol float64
	for k, v := range volumes {
		keys = append(keys, k)
		if v > pocVol {
			pocKey = k
			pocVol = v
		}
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	pocIdx := sort.Search(len(keys), func(i int) bool { return keys[i] >= pocKey })
	lo, hi := pocIdx, pocIdx
	cum := volumes[pocKey]
	target := total * 0.70
	for cum < target && (lo > 0 || hi < len(keys)-1) {
		leftVol := -1.0
		rightVol := -1.0
		if lo > 0 {
			leftVol = volumes[keys[lo-1]]
		}
		if hi < len(keys)-1 {
			rightVol = volumes[keys[hi+1]]
		}
		if rightVol >= leftVol {
			hi++
			cum += volumes[keys[hi]]
		} else {
			lo--
			cum += volumes[keys[lo]]
		}
	}
	return priorValueArea{
		POC: float64(pocKey) * tickSize,
		VAL: float64(keys[lo]) * tickSize,
		VAH: float64(keys[hi]) * tickSize,
		OK:  true,
	}
}

func filterSignalsByRegime(entryBars []bar, sigs []signal, oneMinuteBars []bar, regimeTF int, method string) []signal {
	if len(sigs) == 0 || len(entryBars) == 0 || len(oneMinuteBars) == 0 || regimeTF <= 0 {
		return nil
	}
	htfBars := resample(oneMinuteBars, regimeTF)
	regimes := buildRegimePoints(htfBars, regimeTF, method)
	if len(regimes) == 0 {
		return nil
	}
	out := make([]signal, 0, len(sigs))
	for _, s := range sigs {
		if s.Index < 0 || s.Index >= len(entryBars) {
			continue
		}
		regime, ok := lookupCompletedRegime(regimes, entryBars[s.Index].Time, regimeTF)
		if ok && regime.Dir == s.Dir {
			out = append(out, s)
		}
	}
	return out
}

func filterSignalsBySessionSegment(entryBars []bar, sigs []signal, allowedSegments ...string) []signal {
	if len(sigs) == 0 || len(entryBars) == 0 || len(allowedSegments) == 0 {
		return nil
	}
	allowed := make(map[string]bool, len(allowedSegments))
	for _, segment := range allowedSegments {
		allowed[segment] = true
	}
	out := make([]signal, 0, len(sigs))
	for _, s := range sigs {
		if s.Index < 0 || s.Index >= len(entryBars) {
			continue
		}
		if allowed[sessionSegment(entryBars[s.Index].Time)] {
			out = append(out, s)
		}
	}
	return out
}

func passesOrderFlowFilters(dir int, volRatio, deltaPct, depthImb, minVolRatio, minDepthImb float64, requireVol, requireDelta, requireDepth bool) bool {
	if requireVol && volRatio < minVolRatio {
		return false
	}
	if requireDelta {
		if dir > 0 && deltaPct < 0.10 {
			return false
		}
		if dir < 0 && deltaPct > -0.10 {
			return false
		}
	}
	if requireDepth {
		if dir > 0 && depthImb < minDepthImb {
			return false
		}
		if dir < 0 && depthImb > -minDepthImb {
			return false
		}
	}
	return true
}

func atrSeries(bars []bar, period int) []float64 {
	out := make([]float64, len(bars))
	if period <= 0 || len(bars) == 0 {
		return out
	}
	trs := make([]float64, len(bars))
	for i := range bars {
		if i == 0 {
			trs[i] = bars[i].High - bars[i].Low
			continue
		}
		prevClose := bars[i-1].Close
		trs[i] = math.Max(bars[i].High-bars[i].Low, math.Max(math.Abs(bars[i].High-prevClose), math.Abs(bars[i].Low-prevClose)))
	}
	return smaSeries(trs, period)
}

func smaSeries(values []float64, period int) []float64 {
	out := make([]float64, len(values))
	if period <= 0 {
		return out
	}
	var sum float64
	for i, v := range values {
		sum += v
		if i >= period {
			sum -= values[i-period]
		}
		if i >= period-1 {
			out[i] = sum / float64(period)
		}
	}
	return out
}

func stdSeries(values []float64, period int) []float64 {
	out := make([]float64, len(values))
	if period <= 0 {
		return out
	}
	var sum, sumSq float64
	for i, v := range values {
		sum += v
		sumSq += v * v
		if i >= period {
			old := values[i-period]
			sum -= old
			sumSq -= old * old
		}
		if i >= period-1 {
			mean := sum / float64(period)
			variance := math.Max(0, sumSq/float64(period)-mean*mean)
			out[i] = math.Sqrt(variance)
		}
	}
	return out
}

func rsiSeries(values []float64, period int) []float64 {
	out := make([]float64, len(values))
	if period <= 0 || len(values) < 2 {
		return out
	}
	gains := make([]float64, len(values))
	losses := make([]float64, len(values))
	for i := 1; i < len(values); i++ {
		change := values[i] - values[i-1]
		if change > 0 {
			gains[i] = change
		} else {
			losses[i] = -change
		}
	}
	avgGain := smaSeries(gains, period)
	avgLoss := smaSeries(losses, period)
	for i := period; i < len(values); i++ {
		if avgLoss[i] == 0 {
			out[i] = 100
			continue
		}
		rs := avgGain[i] / avgLoss[i]
		out[i] = 100 - 100/(1+rs)
	}
	return out
}
