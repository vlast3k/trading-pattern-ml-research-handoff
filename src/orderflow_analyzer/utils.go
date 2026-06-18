package main

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"
)

func parseNTTime(s string) (time.Time, bool) {
	s = strings.TrimSpace(s)
	if s == "" {
		return time.Time{}, false
	}
	layouts := []string{
		"2006-01-02 15:04:05.9999999",
		"2006-01-02 15:04:05.999999",
		"2006-01-02 15:04:05",
	}
	for _, layout := range layouts {
		if t, err := time.ParseInLocation(layout, s, ntLocation); err == nil {
			return t, true
		}
	}
	return time.Time{}, false
}

func inferEventTime(raw time.Time, rawOK bool, barTime time.Time) (time.Time, bool, bool) {
	if !rawOK {
		if !barTime.IsZero() {
			return barTime, true, true
		}
		return time.Time{}, false, false
	}
	if raw.Year() < 2000 || raw.Year() > 2100 {
		if !barTime.IsZero() {
			return barTime, true, true
		}
		return time.Time{}, false, false
	}
	return raw, false, true
}

func updateRange(start, end *time.Time, t time.Time) {
	if t.IsZero() {
		return
	}
	if start.IsZero() || t.Before(*start) {
		*start = t
	}
	if end.IsZero() || t.After(*end) {
		*end = t
	}
}

func updateMaxTime(dst *time.Time, t time.Time) {
	if t.IsZero() {
		return
	}
	if dst.IsZero() || t.After(*dst) {
		*dst = t
	}
}

func updateHealthStats(st *stats, rec []string, idx rowIndex, eventTime time.Time, tsOK bool) {
	if tsOK {
		updateMaxTime(&st.LastHealthEvent, eventTime)
	}
	if status := strings.TrimSpace(get(rec, idx.connectionStatus)); status != "" {
		st.LastConnectionStatus = status
	}
	if status := strings.TrimSpace(get(rec, idx.priceStatus)); status != "" {
		st.LastPriceStatus = status
	}
	if state := strings.TrimSpace(get(rec, idx.healthState)); state != "" {
		st.LastHealthState = state
	}
	if detail := strings.TrimSpace(get(rec, idx.healthDetail)); detail != "" {
		st.LastHealthDetail = detail
	}
	if value := parseFloat(get(rec, idx.staleSeconds)); value >= 0 {
		st.LastHealthStaleSeconds = value
		if value > st.MaxHealthStaleSeconds {
			st.MaxHealthStaleSeconds = value
		}
	}
	if t, ok := parseNTTime(get(rec, idx.lastLastTime)); ok {
		updateMaxTime(&st.LastTradeEvent, t)
		updateMaxTime(&st.LastMarketDataEvent, t)
	}
	if t, ok := parseNTTime(get(rec, idx.lastBidTime)); ok {
		updateMaxTime(&st.LastBidEvent, t)
		updateMaxTime(&st.LastMarketDataEvent, t)
	}
	if t, ok := parseNTTime(get(rec, idx.lastAskTime)); ok {
		updateMaxTime(&st.LastAskEvent, t)
		updateMaxTime(&st.LastMarketDataEvent, t)
	}
	if t, ok := parseNTTime(get(rec, idx.lastDepthTime)); ok {
		updateMaxTime(&st.LastDepthEvent, t)
	}
}

func addFeedWarnings(st *stats) {
	lastTradeOrQuote := maxTime(st.LastTradeEvent, maxTime(st.LastBidEvent, st.LastAskEvent))
	if !st.EventEnd.IsZero() && !st.BarEnd.IsZero() {
		lag := st.EventEnd.Sub(st.BarEnd)
		if lag >= staleFeedThreshold {
			st.Warnings = appendWarnings(st.Warnings, fmt.Sprintf("STALE_FEED: latest event timestamp is %s but latest bar_time is %s (%s gap). Rows after that point may be stale or depth-only.", st.EventEnd.Format(time.RFC3339), st.BarEnd.Format(time.RFC3339), formatDuration(lag)))
		}
	}
	if !st.LastDepthEvent.IsZero() && !lastTradeOrQuote.IsZero() {
		lag := st.LastDepthEvent.Sub(lastTradeOrQuote)
		if lag >= staleFeedThreshold {
			st.Warnings = appendWarnings(st.Warnings, fmt.Sprintf("STALE_FEED: depth rows continued until %s but Last/Bid/Ask market data stopped at %s (%s gap).", st.LastDepthEvent.Format(time.RFC3339), lastTradeOrQuote.Format(time.RFC3339), formatDuration(lag)))
		}
	}
	if !st.LastHealthEvent.IsZero() && !lastTradeOrQuote.IsZero() {
		lag := st.LastHealthEvent.Sub(lastTradeOrQuote)
		if lag >= staleFeedThreshold && st.LastHealthState != "ok" {
			st.Warnings = appendWarnings(st.Warnings, fmt.Sprintf("STALE_FEED: exporter health timestamp is %s but Last/Bid/Ask market data stopped at %s (%s gap, state=%s).", st.LastHealthEvent.Format(time.RFC3339), lastTradeOrQuote.Format(time.RFC3339), formatDuration(lag), st.LastHealthState))
		}
	}
	if st.LastHealthState == "stale_market_data" || st.LastHealthState == "price_feed_not_connected" || st.LastHealthState == "no_market_data_seen" {
		st.Warnings = appendWarnings(st.Warnings, fmt.Sprintf("Exporter final health state is %s at %s (%s).", st.LastHealthState, formatTimeOrDash(st.LastHealthEvent), dash(st.LastHealthDetail)))
	}
}

func appendWarnings(dst []string, warnings ...string) []string {
	for _, warning := range warnings {
		warning = strings.TrimSpace(warning)
		if warning == "" {
			continue
		}
		seen := false
		for _, existing := range dst {
			if existing == warning {
				seen = true
				break
			}
		}
		if !seen {
			dst = append(dst, warning)
		}
	}
	return dst
}

func maxTime(left, right time.Time) time.Time {
	if left.IsZero() {
		return right
	}
	if right.IsZero() {
		return left
	}
	if left.After(right) {
		return left
	}
	return right
}

func formatDuration(d time.Duration) string {
	if d < 0 {
		d = -d
	}
	if d >= time.Hour {
		return fmt.Sprintf("%.1fh", d.Hours())
	}
	if d >= time.Minute {
		return fmt.Sprintf("%.1fm", d.Minutes())
	}
	return fmt.Sprintf("%.0fs", d.Seconds())
}

func formatTimeOrDash(t time.Time) string {
	if t.IsZero() {
		return "-"
	}
	return t.Format(time.RFC3339)
}

func dash(s string) string {
	if strings.TrimSpace(s) == "" {
		return "-"
	}
	return s
}

func defaultExportDir() string {
	if configured := strings.TrimSpace(os.Getenv("NINJATRADER_EXPORT_DIR")); configured != "" {
		return configured
	}
	if runtime.GOOS == "windows" {
		if home, err := os.UserHomeDir(); err == nil {
			return filepath.Join(home, "Documents", "NinjaTrader 8", "export")
		}
	}
	if runtime.GOOS == "darwin" {
		return `/Volumes/NinjaTrader 8/export`
	}
	return `/mnt/c/Users/I032581/Documents/NinjaTrader 8/export`
}

func inferPointValue(instrument string) float64 {
	name := strings.ToUpper(strings.TrimSpace(instrument))
	switch {
	case strings.HasPrefix(name, "MNQ"):
		return 2
	case strings.HasPrefix(name, "MES"):
		return 5
	case strings.HasPrefix(name, "NQ"):
		return 20
	case strings.HasPrefix(name, "ES"):
		return 50
	default:
		return 0
	}
}

func discoverLatestExports(dir string) []string {
	matchesByRawPath := make(map[string]string)
	for _, pattern := range []string{
		filepath.Join(dir, "orderflow_*.csv"),
		filepath.Join(dir, "orderflow_*.csv.gz"),
	} {
		matches, err := filepath.Glob(pattern)
		if err != nil {
			continue
		}
		for _, path := range matches {
			key := rawExportPath(path)
			if existing, ok := matchesByRawPath[key]; ok && strings.HasSuffix(strings.ToLower(existing), ".csv") {
				continue
			}
			matchesByRawPath[key] = path
		}
	}
	if len(matchesByRawPath) == 0 {
		return nil
	}
	matches := make([]string, 0, len(matchesByRawPath))
	for _, path := range matchesByRawPath {
		matches = append(matches, path)
	}
	sort.Strings(matches)

	type sessionInfo struct {
		root    string
		session string
		mod     time.Time
		paths   []string
	}
	sessions := make(map[string]map[string]*sessionInfo)
	for _, path := range matches {
		info, err := os.Stat(path)
		if err != nil || info.IsDir() {
			continue
		}
		root := exportRoot(path)
		if root == "" {
			continue
		}
		session := exportSession(path)
		if session == "" {
			continue
		}
		bySession := sessions[root]
		if bySession == nil {
			bySession = make(map[string]*sessionInfo)
			sessions[root] = bySession
		}
		current := bySession[session]
		if current == nil {
			current = &sessionInfo{root: root, session: session}
			bySession[session] = current
		}
		current.paths = append(current.paths, path)
		if info.ModTime().After(current.mod) {
			current.mod = info.ModTime()
		}
	}

	var selected []*sessionInfo
	for _, bySession := range sessions {
		var latest *sessionInfo
		for _, session := range bySession {
			if latest == nil || session.mod.After(latest.mod) {
				latest = session
			}
		}
		if latest != nil {
			selected = append(selected, latest)
		}
	}
	sort.Slice(selected, func(i, j int) bool {
		return selected[i].root < selected[j].root
	})

	var out []string
	for _, session := range selected {
		sort.Strings(session.paths)
		out = append(out, session.paths...)
	}
	return out
}

func discoverExports(dir, source, instrument string) []string {
	source = strings.ToLower(strings.TrimSpace(source))
	instrument = strings.ToUpper(strings.TrimSpace(instrument))
	if source == "" || source == "latest" {
		return filterExportsByInstrument(discoverLatestExports(dir), instrument)
	}
	if source != "live" && source != "replayfill" && source != "all" {
		fmt.Fprintf(os.Stderr, "warning: invalid export source %q; expected latest, live, replayfill, or all\n", source)
		return nil
	}

	matchesByRawPath := make(map[string]string)
	for _, pattern := range []string{
		filepath.Join(dir, "orderflow_*.csv"),
		filepath.Join(dir, "orderflow_*.csv.gz"),
		filepath.Join(dir, "replayfill_orderflow_*.csv"),
		filepath.Join(dir, "replayfill_orderflow_*.csv.gz"),
	} {
		matches, err := filepath.Glob(pattern)
		if err != nil {
			continue
		}
		for _, path := range matches {
			name := strings.ToLower(filepath.Base(path))
			isReplay := strings.HasPrefix(name, "replayfill_orderflow_")
			if (source == "live" && isReplay) || (source == "replayfill" && !isReplay) {
				continue
			}
			if !exportMatchesInstrument(path, instrument) {
				continue
			}
			key := rawExportPath(path)
			if existing, ok := matchesByRawPath[key]; ok && strings.HasSuffix(strings.ToLower(existing), ".csv") {
				continue
			}
			matchesByRawPath[key] = path
		}
	}

	out := make([]string, 0, len(matchesByRawPath))
	for _, path := range matchesByRawPath {
		out = append(out, path)
	}
	sort.Strings(out)
	return out
}

func filterExportsByInstrument(paths []string, instrument string) []string {
	if instrument == "" {
		return paths
	}
	out := make([]string, 0, len(paths))
	for _, path := range paths {
		if exportMatchesInstrument(path, instrument) {
			out = append(out, path)
		}
	}
	return out
}

func exportMatchesInstrument(path, instrument string) bool {
	if instrument == "" {
		return true
	}
	name := strings.ToUpper(filepath.Base(path))
	return strings.HasPrefix(name, "ORDERFLOW_"+instrument+"_") ||
		strings.HasPrefix(name, "REPLAYFILL_ORDERFLOW_"+instrument+"_")
}

func rawExportPath(path string) string {
	lower := strings.ToLower(path)
	if strings.HasSuffix(lower, ".csv.gz") {
		return path[:len(path)-3]
	}
	return path
}

func exportBase(path string) string {
	base := filepath.Base(path)
	lower := strings.ToLower(base)
	switch {
	case strings.HasSuffix(lower, ".csv.gz"):
		return base[:len(base)-len(".csv.gz")]
	case strings.HasSuffix(lower, ".csv"):
		return base[:len(base)-len(".csv")]
	default:
		return strings.TrimSuffix(base, filepath.Ext(base))
	}
}

func exportRoot(path string) string {
	base := exportBase(path)
	parts := strings.Split(base, "_")
	if len(parts) < 2 || parts[0] != "orderflow" {
		return ""
	}
	return strings.ToLower(parts[1])
}

func exportSession(path string) string {
	base := exportBase(path)
	if idx := strings.LastIndex(base, "_part"); idx > 0 {
		base = base[:idx]
		return strings.ToLower(base)
	}
	return ""
}

func parseFloat(s string) float64 {
	v, _ := strconv.ParseFloat(strings.TrimSpace(s), 64)
	return v
}

func parseInt(s string) int64 {
	v, _ := strconv.ParseInt(strings.TrimSpace(s), 10, 64)
	return v
}

func get(rec []string, i int) string {
	if i < 0 || i >= len(rec) {
		return ""
	}
	return rec[i]
}

func winRate(r result) float64 {
	if r.Signals == 0 {
		return 0
	}
	return 100 * float64(r.Wins) / float64(r.Signals)
}

func summaryWinRate(s simSummary) float64 {
	if s.Trades == 0 {
		return 0
	}
	return 100 * float64(s.Wins) / float64(s.Trades)
}

func riskBudgetWinRate(s riskBudgetSummary) float64 {
	if s.Trades == 0 {
		return 0
	}
	return 100 * float64(s.Wins) / float64(s.Trades)
}

func formatPF(v float64) string {
	if math.IsInf(v, 1) {
		return "Inf"
	}
	return fmt.Sprintf("%.3f", v)
}

func formatMoney(v float64) string {
	if math.IsInf(v, 1) {
		return "Inf"
	}
	if math.IsNaN(v) {
		return "NaN"
	}
	if v < 0 {
		return fmt.Sprintf("-$%.2f", -v)
	}
	return fmt.Sprintf("$%.2f", v)
}
