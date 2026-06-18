package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

func writeTradesCSV(path string, trades []trade) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"instrument", "timeframe", "variant", "signal_time", "entry_time", "exit_time",
		"entry_session_time", "session_rollup", "rth_segment", "trading_day",
		"direction", "reason", "level", "entry", "stop", "target", "exit", "outcome",
		"r", "mfe_r", "mae_r", "risk_points", "delta", "delta_pct", "depth_imbalance",
		"wick_ratio", "volume_ratio", "signal_volume", "bid_volume", "ask_volume",
		"depth_bid_churn", "depth_ask_churn", "top_bid_churn", "top_ask_churn",
		"quote_bid_churn", "quote_ask_churn", "bid_quote_updates", "ask_quote_updates",
		"signal_trades", "signal_depth_rows",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, tr := range trades {
		row := []string{
			tr.Instrument,
			strconv.Itoa(tr.Timeframe),
			tr.Variant,
			tr.SignalTime.Format(time.RFC3339),
			tr.EntryTime.Format(time.RFC3339),
			tr.ExitTime.Format(time.RFC3339),
			tr.EntryTime.In(sessionLocation).Format(time.RFC3339),
			sessionRollup(tr.EntryTime),
			sessionSegment(tr.EntryTime),
			tradingDay(tr.EntryTime),
			dirName(tr.Dir),
			tr.Reason,
			fmt.Sprintf("%.4f", tr.Level),
			fmt.Sprintf("%.4f", tr.Entry),
			fmt.Sprintf("%.4f", tr.Stop),
			fmt.Sprintf("%.4f", tr.Target),
			fmt.Sprintf("%.4f", tr.Exit),
			tr.Outcome,
			fmt.Sprintf("%.6f", tr.R),
			fmt.Sprintf("%.6f", tr.MFER),
			fmt.Sprintf("%.6f", tr.MAER),
			fmt.Sprintf("%.4f", tr.RiskPoints),
			strconv.FormatInt(tr.Delta, 10),
			fmt.Sprintf("%.6f", tr.DeltaPct),
			fmt.Sprintf("%.6f", tr.DepthImb),
			fmt.Sprintf("%.6f", tr.WickRatio),
			fmt.Sprintf("%.6f", tr.VolumeRatio),
			strconv.FormatInt(tr.SignalVolume, 10),
			strconv.FormatInt(tr.BidVolume, 10),
			strconv.FormatInt(tr.AskVolume, 10),
			strconv.FormatInt(tr.DepthBid, 10),
			strconv.FormatInt(tr.DepthAsk, 10),
			strconv.FormatInt(tr.TopBid, 10),
			strconv.FormatInt(tr.TopAsk, 10),
			strconv.FormatInt(tr.QuoteBid, 10),
			strconv.FormatInt(tr.QuoteAsk, 10),
			strconv.FormatInt(tr.BidQuotes, 10),
			strconv.FormatInt(tr.AskQuotes, 10),
			strconv.FormatInt(tr.SignalTrades, 10),
			strconv.FormatInt(tr.SignalDepthRows, 10),
		}
		if err := w.Write(row); err != nil {
			return err
		}
	}
	return w.Error()
}

func writeAdvisorCSV(path string, rows []advisorRow) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"timeframe", "variant", "profile", "delay_bars", "miss_rate", "expiry_bars", "max_chase_r",
		"signals", "trades", "missed", "expired", "chase_skipped",
		"wins", "losses", "targets", "stops", "timeouts",
		"win_rate", "avg_r", "total_r", "profit_factor", "max_drawdown_r", "avg_risk_points", "avg_mfe_r", "avg_mae_r",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, row := range rows {
		s := row.Summary
		out := []string{
			strconv.Itoa(row.Timeframe),
			row.Variant,
			row.Profile.Name,
			strconv.Itoa(row.Profile.DelayBars),
			fmt.Sprintf("%.6f", row.Profile.MissRate),
			strconv.Itoa(row.Profile.ExpiryBars),
			fmt.Sprintf("%.6f", row.Profile.MaxChaseR),
			strconv.Itoa(row.Signals),
			strconv.Itoa(s.Trades),
			strconv.Itoa(row.Missed),
			strconv.Itoa(row.Expired),
			strconv.Itoa(row.ChaseSkipped),
			strconv.Itoa(s.Wins),
			strconv.Itoa(s.Losses),
			strconv.Itoa(s.Targets),
			strconv.Itoa(s.Stops),
			strconv.Itoa(s.Timeouts),
			fmt.Sprintf("%.6f", summaryWinRate(s)),
			fmt.Sprintf("%.6f", s.AvgR),
			fmt.Sprintf("%.6f", s.TotalR),
			formatPF(s.ProfitFactor),
			fmt.Sprintf("%.6f", s.MaxDrawdownR),
			fmt.Sprintf("%.6f", s.AvgRiskPoints),
			fmt.Sprintf("%.6f", s.AvgMFER),
			fmt.Sprintf("%.6f", s.AvgMAER),
		}
		if err := w.Write(out); err != nil {
			return err
		}
	}
	return w.Error()
}

func writeRegimeFilterCSV(path string, rows []regimeFilterRow) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"regime_tf", "method", "entry_tf", "variant",
		"baseline_trades", "baseline_win_rate", "baseline_avg_r", "baseline_total_r", "baseline_max_dd_r",
		"aligned_trades", "aligned_win_rate", "aligned_avg_r", "aligned_total_r", "aligned_max_dd_r",
		"against_trades", "against_win_rate", "against_avg_r", "against_total_r", "against_max_dd_r",
		"neutral_trades", "neutral_win_rate", "neutral_avg_r", "neutral_total_r", "neutral_max_dd_r",
		"missing_trades", "kept_pct", "avg_regime_strength", "aligned_total_r_improvement", "aligned_avg_r_improvement",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, row := range rows {
		rec := []string{
			strconv.Itoa(row.Key.RegimeTF),
			row.Key.Method,
			strconv.Itoa(row.Key.EntryTF),
			row.Key.Variant,
			strconv.Itoa(row.Base.Trades),
			fmt.Sprintf("%.6f", summaryWinRate(row.Base)),
			fmt.Sprintf("%.6f", row.Base.AvgR),
			fmt.Sprintf("%.6f", row.Base.TotalR),
			fmt.Sprintf("%.6f", row.Base.MaxDrawdownR),
			strconv.Itoa(row.Aligned.Trades),
			fmt.Sprintf("%.6f", summaryWinRate(row.Aligned)),
			fmt.Sprintf("%.6f", row.Aligned.AvgR),
			fmt.Sprintf("%.6f", row.Aligned.TotalR),
			fmt.Sprintf("%.6f", row.Aligned.MaxDrawdownR),
			strconv.Itoa(row.Against.Trades),
			fmt.Sprintf("%.6f", summaryWinRate(row.Against)),
			fmt.Sprintf("%.6f", row.Against.AvgR),
			fmt.Sprintf("%.6f", row.Against.TotalR),
			fmt.Sprintf("%.6f", row.Against.MaxDrawdownR),
			strconv.Itoa(row.Neutral.Trades),
			fmt.Sprintf("%.6f", summaryWinRate(row.Neutral)),
			fmt.Sprintf("%.6f", row.Neutral.AvgR),
			fmt.Sprintf("%.6f", row.Neutral.TotalR),
			fmt.Sprintf("%.6f", row.Neutral.MaxDrawdownR),
			strconv.Itoa(row.Missing),
			fmt.Sprintf("%.6f", row.KeptPct),
			fmt.Sprintf("%.6f", row.AvgPower),
			fmt.Sprintf("%.6f", row.Aligned.TotalR-row.Base.TotalR),
			fmt.Sprintf("%.6f", row.Aligned.AvgR-row.Base.AvgR),
		}
		if err := w.Write(rec); err != nil {
			return err
		}
	}
	return w.Error()
}

func writeRegimeTradeCSV(path string, rows []regimeTradeRow) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"regime_tf", "method", "alignment", "regime_time", "regime_session_time",
		"regime_direction", "regime_label", "regime_strength",
		"instrument", "entry_tf", "variant", "signal_time", "entry_time", "exit_time",
		"entry_session_time", "trading_day", "session_rollup", "rth_segment",
		"direction", "reason", "outcome", "r", "mfe_r", "mae_r", "risk_points",
		"level", "entry", "stop", "target", "exit", "delta_pct", "volume_ratio",
		"depth_imbalance", "signal_volume", "signal_trades", "signal_depth_rows",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, row := range rows {
		tr := row.Trade
		regimeTime := ""
		regimeSessionTime := ""
		if !row.RegimeTime.IsZero() {
			regimeTime = row.RegimeTime.Format(time.RFC3339)
			regimeSessionTime = row.RegimeTime.In(sessionLocation).Format(time.RFC3339)
		}
		rec := []string{
			strconv.Itoa(row.RegimeTF),
			row.Method,
			row.Alignment,
			regimeTime,
			regimeSessionTime,
			dirName(row.RegimeDir),
			row.RegimeLabel,
			fmt.Sprintf("%.6f", row.RegimeStrength),
			tr.Instrument,
			strconv.Itoa(tr.Timeframe),
			tr.Variant,
			tr.SignalTime.Format(time.RFC3339),
			tr.EntryTime.Format(time.RFC3339),
			tr.ExitTime.Format(time.RFC3339),
			tr.EntryTime.In(sessionLocation).Format(time.RFC3339),
			tradingDay(tr.EntryTime),
			sessionRollup(tr.EntryTime),
			sessionSegment(tr.EntryTime),
			dirName(tr.Dir),
			tr.Reason,
			tr.Outcome,
			fmt.Sprintf("%.6f", tr.R),
			fmt.Sprintf("%.6f", tr.MFER),
			fmt.Sprintf("%.6f", tr.MAER),
			fmt.Sprintf("%.4f", tr.RiskPoints),
			fmt.Sprintf("%.4f", tr.Level),
			fmt.Sprintf("%.4f", tr.Entry),
			fmt.Sprintf("%.4f", tr.Stop),
			fmt.Sprintf("%.4f", tr.Target),
			fmt.Sprintf("%.4f", tr.Exit),
			fmt.Sprintf("%.6f", tr.DeltaPct),
			fmt.Sprintf("%.6f", tr.VolumeRatio),
			fmt.Sprintf("%.6f", tr.DepthImb),
			strconv.FormatInt(tr.SignalVolume, 10),
			strconv.FormatInt(tr.SignalTrades, 10),
			strconv.FormatInt(tr.SignalDepthRows, 10),
		}
		if err := w.Write(rec); err != nil {
			return err
		}
	}
	return w.Error()
}

func writeDayRegimeCSV(path string, rows []dayRegime) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"trading_day", "open_time", "complete", "prior_rth_close", "rth_open",
		"gap_points", "gap_pct", "or5_range", "or15_range", "or30_range",
		"or5_return", "or15_return", "or30_return",
		"or5_volume", "or15_volume", "or30_volume",
		"or5_bars", "or15_bars", "or30_bars",
		"or30_range_z", "or30_volume_z",
		"gap_label", "bias_label", "range_label", "volume_label", "regime_label",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, row := range rows {
		openTime := ""
		if !row.OpenTime.IsZero() {
			openTime = row.OpenTime.Format(time.RFC3339)
		}
		rec := []string{
			row.Day,
			openTime,
			strconv.FormatBool(row.Complete),
			fmt.Sprintf("%.6f", row.PriorClose),
			fmt.Sprintf("%.6f", row.Open),
			fmt.Sprintf("%.6f", row.GapPoints),
			fmt.Sprintf("%.6f", row.GapPct),
			fmt.Sprintf("%.6f", row.OR5Range),
			fmt.Sprintf("%.6f", row.OR15Range),
			fmt.Sprintf("%.6f", row.OR30Range),
			fmt.Sprintf("%.6f", row.OR5Return),
			fmt.Sprintf("%.6f", row.OR15Return),
			fmt.Sprintf("%.6f", row.OR30Return),
			strconv.FormatInt(row.OR5Volume, 10),
			strconv.FormatInt(row.OR15Volume, 10),
			strconv.FormatInt(row.OR30Volume, 10),
			strconv.Itoa(row.OR5Bars),
			strconv.Itoa(row.OR15Bars),
			strconv.Itoa(row.OR30Bars),
			fmt.Sprintf("%.6f", row.OR30RangeZ),
			fmt.Sprintf("%.6f", row.OR30VolumeZ),
			row.GapLabel,
			row.BiasLabel,
			row.RangeLabel,
			row.VolumeLabel,
			row.RegimeLabel,
		}
		if err := w.Write(rec); err != nil {
			return err
		}
	}
	return w.Error()
}

func writeDayRegimeStrategyCSV(path string, rows []dayRegimeStrategyRow) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"regime", "timeframe", "variant",
		"trades", "win_rate", "avg_r", "total_r", "profit_factor", "max_drawdown_r",
		"pnl_usd", "max_drawdown_usd", "days", "positive_days", "negative_days",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, row := range rows {
		s := row.Summary.Summary
		rec := []string{
			row.Key.Regime,
			strconv.Itoa(row.Key.Timeframe),
			row.Key.Variant,
			strconv.Itoa(s.Trades),
			fmt.Sprintf("%.6f", summaryWinRate(s)),
			fmt.Sprintf("%.6f", s.AvgR),
			fmt.Sprintf("%.6f", s.TotalR),
			formatPF(s.ProfitFactor),
			fmt.Sprintf("%.6f", s.MaxDrawdownR),
			fmt.Sprintf("%.6f", row.Summary.Dollars),
			fmt.Sprintf("%.6f", row.Summary.MaxDrawdown),
			strconv.Itoa(row.Summary.Days),
			strconv.Itoa(row.Summary.PositiveDays),
			strconv.Itoa(row.Summary.NegativeDays),
		}
		if err := w.Write(rec); err != nil {
			return err
		}
	}
	return w.Error()
}

func writeDayRegimeSelectorCSV(path string, rows []dayRegimeSelectorRow) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()

	header := []string{
		"trading_day", "regime", "mode", "source", "timeframe", "variant",
		"prior_trades", "prior_total_r", "prior_avg_r",
		"day_trades", "day_win_rate", "day_avg_r", "day_total_r", "day_profit_factor", "day_max_drawdown_r",
		"day_pnl_usd", "day_max_drawdown_usd",
	}
	if err := w.Write(header); err != nil {
		return err
	}
	for _, row := range rows {
		s := row.Summary.Summary
		rec := []string{
			row.Day,
			row.Regime,
			row.Mode,
			row.Source,
			strconv.Itoa(row.Timeframe),
			row.Variant,
			strconv.Itoa(row.PriorTrades),
			fmt.Sprintf("%.6f", row.PriorTotalR),
			fmt.Sprintf("%.6f", row.PriorAvgR),
			strconv.Itoa(s.Trades),
			fmt.Sprintf("%.6f", summaryWinRate(s)),
			fmt.Sprintf("%.6f", s.AvgR),
			fmt.Sprintf("%.6f", s.TotalR),
			formatPF(s.ProfitFactor),
			fmt.Sprintf("%.6f", s.MaxDrawdownR),
			fmt.Sprintf("%.6f", row.Summary.Dollars),
			fmt.Sprintf("%.6f", row.Summary.MaxDrawdown),
		}
		if err := w.Write(rec); err != nil {
			return err
		}
	}
	return w.Error()
}

func dirName(dir int) string {
	if dir > 0 {
		return "long"
	}
	if dir < 0 {
		return "short"
	}
	return "neutral"
}

func safeName(s string) string {
	s = strings.TrimSpace(strings.ToLower(s))
	var b strings.Builder
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		} else if b.Len() > 0 && b.String()[b.Len()-1] != '_' {
			b.WriteByte('_')
		}
	}
	return strings.Trim(b.String(), "_")
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
