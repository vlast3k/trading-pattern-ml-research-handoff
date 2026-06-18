package main

import (
	"bufio"
	"compress/gzip"
	"encoding/csv"
	"encoding/gob"
	"fmt"
	"hash/fnv"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

func readDatasets(files []string, depthLevels int, cacheDir string, readWorkers int) []dataset {
	sort.Strings(files)
	results := readExportFiles(files, depthLevels, cacheDir, readWorkers)
	groups := make(map[string]*dataset)
	var keys []string
	for _, result := range results {
		file := result.File
		if result.Cached {
			fmt.Printf("Reading %s (bar cache hit)\n", file)
		} else {
			fmt.Printf("Reading %s\n", file)
		}
		if result.Err != nil {
			fmt.Fprintf(os.Stderr, "error reading %s: %v\n", file, result.Err)
			continue
		}
		bars := result.Bars
		st := result.Stats
		key := safeName(st.Instrument)
		if key == "" {
			key = exportRoot(file)
		}
		if key == "" {
			key = safeName(strings.TrimSuffix(filepath.Base(file), filepath.Ext(file)))
		}
		ds := groups[key]
		if ds == nil {
			ds = &dataset{Key: key}
			groups[key] = ds
			keys = append(keys, key)
		}
		ds.Files = append(ds.Files, file)
		ds.Bars = append(ds.Bars, bars...)
		mergeStats(&ds.Stats, st)
		fmt.Printf("  rows=%d bars=%d trades=%d quotes=%d depth=%d health=%d bad=%d\n", st.Rows, len(bars), st.TradeRows, st.QuoteRows, st.DepthRows, st.HealthRows+st.ConnectionStatusRows, st.BadRows)
		for _, warning := range st.Warnings {
			fmt.Printf("  warning: %s\n", warning)
		}
	}
	sort.Strings(keys)
	out := make([]dataset, 0, len(keys))
	for _, key := range keys {
		ds := groups[key]
		ds.Bars = mergeBars(ds.Bars)
		out = append(out, *ds)
	}
	return out
}

func readExportFiles(files []string, depthLevels int, cacheDir string, readWorkers int) []fileReadResult {
	if readWorkers < 1 {
		readWorkers = 1
	}
	if readWorkers == 1 || len(files) <= 1 {
		results := make([]fileReadResult, 0, len(files))
		for i, file := range files {
			bars, st, cached, err := readExportCached(file, depthLevels, cacheDir)
			results = append(results, fileReadResult{
				Index:  i,
				File:   file,
				Bars:   bars,
				Stats:  st,
				Err:    err,
				Cached: cached,
			})
		}
		return results
	}

	jobs := make(chan fileReadResult)
	results := make([]fileReadResult, 0, len(files))
	var mu sync.Mutex
	var wg sync.WaitGroup
	for worker := 0; worker < readWorkers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for job := range jobs {
				bars, st, cached, err := readExportCached(job.File, depthLevels, cacheDir)
				job.Bars = bars
				job.Stats = st
				job.Cached = cached
				job.Err = err
				mu.Lock()
				results = append(results, job)
				mu.Unlock()
			}
		}()
	}
	for i, file := range files {
		jobs <- fileReadResult{Index: i, File: file}
	}
	close(jobs)
	wg.Wait()
	sort.Slice(results, func(i, j int) bool {
		return results[i].Index < results[j].Index
	})
	return results
}

func mergeStats(dst *stats, src stats) {
	if dst.Instrument == "" {
		dst.Instrument = src.Instrument
	}
	if dst.TimeSource == "" {
		dst.TimeSource = src.TimeSource
	} else if src.TimeSource != "" && dst.TimeSource != src.TimeSource {
		dst.TimeSource = "mixed"
	}
	if dst.File == "" {
		dst.File = src.File
	} else if src.File != "" {
		dst.File += ";" + src.File
	}
	dst.Rows += src.Rows
	dst.BadRows += src.BadRows
	dst.IncompleteTailRows += src.IncompleteTailRows
	dst.BadTimestampRows += src.BadTimestampRows
	dst.RepairedTimestampRows += src.RepairedTimestampRows
	dst.TradeRows += src.TradeRows
	dst.QuoteRows += src.QuoteRows
	dst.DepthRows += src.DepthRows
	dst.HealthRows += src.HealthRows
	dst.ConnectionStatusRows += src.ConnectionStatusRows
	updateRange(&dst.EventStart, &dst.EventEnd, src.EventStart)
	updateRange(&dst.EventStart, &dst.EventEnd, src.EventEnd)
	updateRange(&dst.BarStart, &dst.BarEnd, src.BarStart)
	updateRange(&dst.BarStart, &dst.BarEnd, src.BarEnd)
	updateMaxTime(&dst.LastTradeEvent, src.LastTradeEvent)
	updateMaxTime(&dst.LastBidEvent, src.LastBidEvent)
	updateMaxTime(&dst.LastAskEvent, src.LastAskEvent)
	updateMaxTime(&dst.LastDepthEvent, src.LastDepthEvent)
	updateMaxTime(&dst.LastMarketDataEvent, src.LastMarketDataEvent)
	if !src.LastHealthEvent.IsZero() && (dst.LastHealthEvent.IsZero() || src.LastHealthEvent.After(dst.LastHealthEvent)) {
		dst.LastHealthEvent = src.LastHealthEvent
		dst.LastConnectionStatus = src.LastConnectionStatus
		dst.LastPriceStatus = src.LastPriceStatus
		dst.LastHealthState = src.LastHealthState
		dst.LastHealthDetail = src.LastHealthDetail
		dst.LastHealthStaleSeconds = src.LastHealthStaleSeconds
	} else if dst.LastHealthEvent.IsZero() {
		if src.LastConnectionStatus != "" {
			dst.LastConnectionStatus = src.LastConnectionStatus
		}
		if src.LastPriceStatus != "" {
			dst.LastPriceStatus = src.LastPriceStatus
		}
		if src.LastHealthState != "" {
			dst.LastHealthState = src.LastHealthState
		}
		if src.LastHealthDetail != "" {
			dst.LastHealthDetail = src.LastHealthDetail
		}
		dst.LastHealthStaleSeconds = src.LastHealthStaleSeconds
	}
	if src.MaxHealthStaleSeconds > dst.MaxHealthStaleSeconds {
		dst.MaxHealthStaleSeconds = src.MaxHealthStaleSeconds
	}
	dst.Warnings = appendWarnings(dst.Warnings, src.Warnings...)
}

func mergeBars(in []bar) []bar {
	if len(in) == 0 {
		return nil
	}
	sort.SliceStable(in, func(i, j int) bool {
		if !in[i].Time.Equal(in[j].Time) {
			return in[i].Time.Before(in[j].Time)
		}
		return in[i].SourceRank < in[j].SourceRank
	})
	out := make([]bar, 0, len(in))
	for _, x := range in {
		if x.Time.IsZero() {
			continue
		}
		if len(out) == 0 || !out[len(out)-1].Time.Equal(x.Time) {
			out = append(out, x)
			continue
		}
		if out[len(out)-1].SourceRank != x.SourceRank {
			continue
		}
		mergeBar(&out[len(out)-1], x)
	}
	return out
}

func mergeBar(dst *bar, src bar) {
	if dst.Open == 0 {
		dst.Open = src.Open
	}
	if src.High > dst.High {
		dst.High = src.High
	}
	if src.Low < dst.Low || dst.Low == 0 {
		dst.Low = src.Low
	}
	if src.Close != 0 {
		dst.Close = src.Close
	}
	if src.Volume > dst.Volume {
		dst.Volume = src.Volume
	}
	dst.BidVolume += src.BidVolume
	dst.AskVolume += src.AskVolume
	dst.Trades += src.Trades
	dst.QuoteRows += src.QuoteRows
	dst.DepthRows += src.DepthRows
	dst.UnknownVol += src.UnknownVol
	dst.DepthBid += src.DepthBid
	dst.DepthAsk += src.DepthAsk
	dst.TopBid += src.TopBid
	dst.TopAsk += src.TopAsk
	dst.QuoteBid += src.QuoteBid
	dst.QuoteAsk += src.QuoteAsk
	dst.BidQuotes += src.BidQuotes
	dst.AskQuotes += src.AskQuotes
}

type compositeReadCloser struct {
	io.Reader
	closers []io.Closer
}

func (rc *compositeReadCloser) Close() error {
	var firstErr error
	for _, closer := range rc.closers {
		if err := closer.Close(); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}

func openMaybeGzip(path string) (io.ReadCloser, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	if !strings.HasSuffix(strings.ToLower(path), ".gz") {
		return f, nil
	}
	gz, err := gzip.NewReader(f)
	if err != nil {
		_ = f.Close()
		return nil, err
	}
	return &compositeReadCloser{
		Reader:  gz,
		closers: []io.Closer{gz, f},
	}, nil
}

const barCacheVersion = 2

func readExportCached(path string, depthLevels int, cacheDir string) ([]bar, stats, bool, error) {
	if strings.TrimSpace(cacheDir) == "" {
		bars, st, err := readExport(path, depthLevels)
		annotateBarSource(path, bars)
		return bars, st, false, err
	}

	before, err := os.Stat(path)
	if err != nil {
		return nil, stats{}, false, err
	}
	cachePath := barCachePath(cacheDir, path)
	if bars, st, ok := loadBarCache(cachePath, path, before, depthLevels); ok {
		annotateBarSource(path, bars)
		return bars, st, true, nil
	}

	bars, st, err := readExport(path, depthLevels)
	annotateBarSource(path, bars)
	if err != nil {
		return bars, st, false, err
	}

	after, statErr := os.Stat(path)
	if statErr == nil && sameFileIdentity(before, after) && st.IncompleteTailRows == 0 {
		if err := saveBarCache(cachePath, path, after, depthLevels, bars, st); err != nil {
			fmt.Fprintf(os.Stderr, "warning: could not write bar cache %s: %v\n", cachePath, err)
		}
	}
	return bars, st, false, nil
}

func annotateBarSource(path string, bars []bar) {
	rank := sourceRank(path)
	for i := range bars {
		bars[i].SourceRank = rank
	}
}

func sourceRank(path string) int {
	name := strings.ToLower(filepath.Base(path))
	if strings.HasPrefix(name, "replayfill_orderflow_") {
		return 1
	}
	return 0
}

func loadBarCache(cachePath, sourcePath string, sourceInfo os.FileInfo, depthLevels int) ([]bar, stats, bool) {
	f, err := os.Open(cachePath)
	if err != nil {
		return nil, stats{}, false
	}
	defer f.Close()

	var cf barCacheFile
	if err := gob.NewDecoder(bufio.NewReaderSize(f, 1024*1024)).Decode(&cf); err != nil {
		return nil, stats{}, false
	}
	if cf.Version != barCacheVersion {
		return nil, stats{}, false
	}
	if cf.SourcePath != sourcePath ||
		cf.SourceSize != sourceInfo.Size() ||
		cf.SourceModUnixNano != sourceInfo.ModTime().UnixNano() ||
		cf.DepthLevels != depthLevels ||
		cf.Timezone != ntLocation.String() ||
		cf.StaleThresholdNano != int64(staleFeedThreshold) {
		return nil, stats{}, false
	}
	return cf.Bars, cf.Stats, true
}

func saveBarCache(cachePath, sourcePath string, sourceInfo os.FileInfo, depthLevels int, bars []bar, st stats) error {
	if err := os.MkdirAll(filepath.Dir(cachePath), 0755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(cachePath), filepath.Base(cachePath)+".tmp.")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	cf := barCacheFile{
		Version:            barCacheVersion,
		SourcePath:         sourcePath,
		SourceSize:         sourceInfo.Size(),
		SourceModUnixNano:  sourceInfo.ModTime().UnixNano(),
		DepthLevels:        depthLevels,
		Timezone:           ntLocation.String(),
		StaleThresholdNano: int64(staleFeedThreshold),
		Bars:               bars,
		Stats:              st,
	}
	bw := bufio.NewWriterSize(tmp, 1024*1024)
	encErr := gob.NewEncoder(bw).Encode(cf)
	flushErr := bw.Flush()
	closeErr := tmp.Close()
	if encErr != nil {
		_ = os.Remove(tmpName)
		return encErr
	}
	if flushErr != nil {
		_ = os.Remove(tmpName)
		return flushErr
	}
	if closeErr != nil {
		_ = os.Remove(tmpName)
		return closeErr
	}
	return os.Rename(tmpName, cachePath)
}

func sameFileIdentity(a, b os.FileInfo) bool {
	return a.Size() == b.Size() && a.ModTime().Equal(b.ModTime())
}

func barCachePath(cacheDir, sourcePath string) string {
	h := fnv.New64a()
	_, _ = h.Write([]byte(sourcePath))
	base := safeName(exportBase(sourcePath))
	if base == "" {
		base = "export"
	}
	return filepath.Join(cacheDir, fmt.Sprintf("%s_%016x.gob", base, h.Sum64()))
}

func readExport(path string, depthLevels int) ([]bar, stats, error) {
	sourceSize := int64(-1)
	if info, err := os.Stat(path); err == nil {
		sourceSize = info.Size()
	}
	allowLiveTail := !strings.HasSuffix(strings.ToLower(path), ".gz")

	rc, err := openMaybeGzip(path)
	if err != nil {
		return nil, stats{}, err
	}
	defer rc.Close()

	br := bufio.NewReaderSize(rc, 8*1024*1024)
	r := csv.NewReader(br)
	r.FieldsPerRecord = -1
	r.ReuseRecord = true

	header, err := r.Read()
	if err != nil {
		return nil, stats{}, err
	}
	idx := buildIndex(header)
	if idx.barTime < 0 || idx.barOpen < 0 || idx.barHigh < 0 || idx.barLow < 0 || idx.barClose < 0 {
		return nil, stats{}, fmt.Errorf("missing required bar columns")
	}

	st := stats{File: path}
	byBarTime := make(map[time.Time]*bar, 8192)
	byEventTime := make(map[time.Time]*bar, 8192)
	var barOrdered []time.Time
	var eventOrdered []time.Time

	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		st.Rows++
		if err != nil {
			if isIncompleteLiveTail(r, rec, idx, sourceSize, allowLiveTail) {
				st.IncompleteTailRows++
				break
			}
			st.BadRows++
			continue
		}
		if len(rec) <= idx.barClose {
			if isIncompleteLiveTail(r, rec, idx, sourceSize, allowLiveTail) {
				st.IncompleteTailRows++
				break
			}
			st.BadRows++
			continue
		}

		if st.Instrument == "" {
			st.Instrument = get(rec, idx.instrument)
		}
		eventType := get(rec, idx.eventType)
		mdType := get(rec, idx.marketDataType)
		bt, barOK := parseNTTime(get(rec, idx.barTime))
		rawTs, rawOK := parseNTTime(get(rec, idx.timestamp))
		ts, repaired, tsOK := inferEventTime(rawTs, rawOK, bt)
		if repaired {
			st.RepairedTimestampRows++
		}
		if !tsOK {
			st.BadTimestampRows++
		} else {
			updateRange(&st.EventStart, &st.EventEnd, ts)
		}

		if eventType == "feed_health" || eventType == "connection_status" {
			if eventType == "feed_health" {
				st.HealthRows++
			} else {
				st.ConnectionStatusRows++
			}
			updateHealthStats(&st, rec, idx, ts, tsOK)
			continue
		}

		if !barOK {
			if isIncompleteLiveTail(r, rec, idx, sourceSize, allowLiveTail) {
				st.IncompleteTailRows++
				break
			}
			st.BadRows++
			continue
		}
		updateRange(&st.BarStart, &st.BarEnd, bt)

		b := getOrCreateBar(byBarTime, &barOrdered, bt)

		b.Open = parseFloat(get(rec, idx.barOpen))
		b.High = parseFloat(get(rec, idx.barHigh))
		b.Low = parseFloat(get(rec, idx.barLow))
		b.Close = parseFloat(get(rec, idx.barClose))
		b.Volume = parseInt(get(rec, idx.barVolume))

		var eb *bar
		if tsOK {
			eb = getOrCreateBar(byEventTime, &eventOrdered, eventMinuteClose(ts))
		}

		side := get(rec, idx.side)
		vol := parseInt(get(rec, idx.volume))
		switch eventType {
		case "market_depth":
			st.DepthRows++
			updateMaxTime(&st.LastDepthEvent, ts)
			pos := parseInt(get(rec, idx.position))
			updateDepthBar(b, mdType, pos, vol, depthLevels)
			if eb != nil {
				updateDepthBar(eb, mdType, pos, vol, depthLevels)
			}
		case "market_data":
			updateMaxTime(&st.LastMarketDataEvent, ts)
			if mdType == "Last" {
				st.TradeRows++
				updateMaxTime(&st.LastTradeEvent, ts)
				updateTradeSideBar(b, side, vol)
				if eb != nil {
					updateEventTradeOHLC(eb, parseFloat(get(rec, idx.price)), vol)
					updateTradeSideBar(eb, side, vol)
				}
			} else {
				st.QuoteRows++
				if mdType == "Bid" {
					updateMaxTime(&st.LastBidEvent, ts)
				}
				if mdType == "Ask" {
					updateMaxTime(&st.LastAskEvent, ts)
				}
				updateQuoteBar(b, mdType, vol)
				if eb != nil {
					updateQuoteBar(eb, mdType, vol)
				}
			}
		}
	}

	barTimeBars := barsFromOrdered(barOrdered, byBarTime)
	eventTimeBars := barsFromOrdered(eventOrdered, byEventTime)
	bars := barTimeBars
	st.TimeSource = "bar_time"
	if shouldUseEventTimeBars(barTimeBars, eventTimeBars) {
		bars = eventTimeBars
		st.TimeSource = "event_timestamp_1m"
	}
	setStatsBarRange(&st, bars)
	addFeedWarnings(&st)
	return bars, st, nil
}

func getOrCreateBar(byTime map[time.Time]*bar, ordered *[]time.Time, t time.Time) *bar {
	b := byTime[t]
	if b != nil {
		return b
	}
	b = &bar{Time: t}
	byTime[t] = b
	*ordered = append(*ordered, t)
	return b
}

func isIncompleteLiveTail(r *csv.Reader, rec []string, idx rowIndex, sourceSize int64, allowLiveTail bool) bool {
	if !allowLiveTail || sourceSize <= 0 {
		return false
	}
	offset := r.InputOffset()
	if offset <= 0 || offset < sourceSize {
		return false
	}
	if len(rec) <= idx.barClose {
		return true
	}
	if strings.TrimSpace(get(rec, idx.timestamp)) == "" {
		return true
	}
	if strings.TrimSpace(get(rec, idx.instrument)) == "" {
		return true
	}
	if strings.TrimSpace(get(rec, idx.barTime)) == "" {
		return true
	}
	if _, ok := parseNTTime(get(rec, idx.barTime)); !ok {
		return true
	}
	return false
}

func eventMinuteClose(t time.Time) time.Time {
	return t.Truncate(time.Minute).Add(time.Minute)
}

func updateEventTradeOHLC(b *bar, price float64, vol int64) {
	if price <= 0 {
		return
	}
	if b.Open == 0 {
		b.Open = price
		b.High = price
		b.Low = price
	}
	if price > b.High {
		b.High = price
	}
	if price < b.Low || b.Low == 0 {
		b.Low = price
	}
	b.Close = price
	b.Volume += vol
}

func updateTradeSideBar(b *bar, side string, vol int64) {
	b.Trades++
	switch side {
	case "buy":
		b.AskVolume += vol
	case "sell":
		b.BidVolume += vol
	default:
		b.UnknownVol += vol
	}
}

func updateQuoteBar(b *bar, mdType string, vol int64) {
	b.QuoteRows++
	switch mdType {
	case "Bid":
		b.BidQuotes++
		b.QuoteBid += vol
	case "Ask":
		b.AskQuotes++
		b.QuoteAsk += vol
	}
}

func updateDepthBar(b *bar, mdType string, pos, vol int64, depthLevels int) {
	b.DepthRows++
	switch mdType {
	case "Bid":
		b.DepthBid += vol
		if pos >= 0 && pos < int64(depthLevels) {
			b.TopBid += vol
		}
	case "Ask":
		b.DepthAsk += vol
		if pos >= 0 && pos < int64(depthLevels) {
			b.TopAsk += vol
		}
	}
}

func barsFromOrdered(ordered []time.Time, byTime map[time.Time]*bar) []bar {
	bars := make([]bar, 0, len(ordered))
	for _, t := range ordered {
		b := byTime[t]
		if isValidBar(*b) {
			bars = append(bars, *b)
		}
	}
	return bars
}

func isValidBar(b bar) bool {
	return !b.Time.IsZero() &&
		b.Open > 0 &&
		b.High > 0 &&
		b.Low > 0 &&
		b.Close > 0 &&
		b.High >= b.Low &&
		b.High >= b.Open &&
		b.High >= b.Close &&
		b.Low <= b.Open &&
		b.Low <= b.Close
}

func shouldUseEventTimeBars(barTimeBars, eventTimeBars []bar) bool {
	if len(eventTimeBars) < 3 {
		return false
	}
	if len(barTimeBars) == 0 {
		return true
	}
	if len(barTimeBars) <= 2 && len(eventTimeBars) >= 10 {
		return true
	}
	return len(eventTimeBars) >= len(barTimeBars)*5 && len(eventTimeBars)-len(barTimeBars) >= 20
}

func setStatsBarRange(st *stats, bars []bar) {
	st.BarStart = time.Time{}
	st.BarEnd = time.Time{}
	for _, b := range bars {
		updateRange(&st.BarStart, &st.BarEnd, b.Time)
	}
}

func buildIndex(header []string) rowIndex {
	idx := rowIndex{
		timestamp:        -1,
		instrument:       -1,
		eventType:        -1,
		marketDataType:   -1,
		operation:        -1,
		position:         -1,
		price:            -1,
		volume:           -1,
		bid:              -1,
		ask:              -1,
		side:             -1,
		bidVolume:        -1,
		askVolume:        -1,
		barTime:          -1,
		barOpen:          -1,
		barHigh:          -1,
		barLow:           -1,
		barClose:         -1,
		barVolume:        -1,
		connectionStatus: -1,
		priceStatus:      -1,
		lastLastTime:     -1,
		lastBidTime:      -1,
		lastAskTime:      -1,
		lastDepthTime:    -1,
		healthState:      -1,
		healthDetail:     -1,
		staleSeconds:     -1,
	}
	for i, h := range header {
		switch strings.TrimSpace(h) {
		case "timestamp":
			idx.timestamp = i
		case "instrument":
			idx.instrument = i
		case "event_type":
			idx.eventType = i
		case "market_data_type":
			idx.marketDataType = i
		case "operation":
			idx.operation = i
		case "position":
			idx.position = i
		case "price":
			idx.price = i
		case "volume":
			idx.volume = i
		case "bid":
			idx.bid = i
		case "ask":
			idx.ask = i
		case "side":
			idx.side = i
		case "bid_volume":
			idx.bidVolume = i
		case "ask_volume":
			idx.askVolume = i
		case "bar_time":
			idx.barTime = i
		case "bar_open":
			idx.barOpen = i
		case "bar_high":
			idx.barHigh = i
		case "bar_low":
			idx.barLow = i
		case "bar_close":
			idx.barClose = i
		case "bar_volume":
			idx.barVolume = i
		case "connection_status":
			idx.connectionStatus = i
		case "price_status":
			idx.priceStatus = i
		case "last_last_time":
			idx.lastLastTime = i
		case "last_bid_time":
			idx.lastBidTime = i
		case "last_ask_time":
			idx.lastAskTime = i
		case "last_depth_time":
			idx.lastDepthTime = i
		case "health_state":
			idx.healthState = i
		case "health_detail":
			idx.healthDetail = i
		case "stale_seconds":
			idx.staleSeconds = i
		}
	}
	return idx
}
