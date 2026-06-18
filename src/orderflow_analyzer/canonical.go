package main

import (
	"bufio"
	"compress/gzip"
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

type canonicalReadResult struct {
	index int
	path  string
	bars  []bar
	stats stats
	err   error
}

func readCanonicalDatasets(dir, instrument string, depthLevels, readWorkers int) []dataset {
	files, _ := filepath.Glob(filepath.Join(dir, "canonical_*_1s.csv.gz"))
	instrument = strings.ToLower(strings.TrimSpace(instrument))
	if instrument != "" {
		prefix := "canonical_" + instrument + "_"
		filtered := files[:0]
		for _, path := range files {
			if strings.HasPrefix(strings.ToLower(filepath.Base(path)), prefix) {
				filtered = append(filtered, path)
			}
		}
		files = filtered
	}
	sort.Strings(files)
	if len(files) == 0 {
		return nil
	}
	if readWorkers < 1 {
		readWorkers = 1
	}

	jobs := make(chan canonicalReadResult)
	results := make([]canonicalReadResult, 0, len(files))
	var mu sync.Mutex
	var wg sync.WaitGroup
	for worker := 0; worker < readWorkers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for job := range jobs {
				job.bars, job.stats, job.err = readCanonicalPartition(job.path, depthLevels)
				mu.Lock()
				results = append(results, job)
				mu.Unlock()
			}
		}()
	}
	for i, path := range files {
		jobs <- canonicalReadResult{index: i, path: path}
	}
	close(jobs)
	wg.Wait()
	sort.Slice(results, func(i, j int) bool { return results[i].index < results[j].index })

	groups := make(map[string]*dataset)
	var keys []string
	for _, result := range results {
		if result.err != nil {
			fmt.Fprintf(os.Stderr, "error reading canonical partition %s: %v\n", result.path, result.err)
			continue
		}
		key := safeName(result.stats.Instrument)
		if key == "" {
			continue
		}
		ds := groups[key]
		if ds == nil {
			ds = &dataset{Key: key}
			groups[key] = ds
			keys = append(keys, key)
		}
		ds.Files = append(ds.Files, result.path)
		ds.Bars = append(ds.Bars, result.bars...)
		mergeStats(&ds.Stats, result.stats)
	}
	sort.Strings(keys)
	out := make([]dataset, 0, len(keys))
	for _, key := range keys {
		ds := groups[key]
		sort.Slice(ds.Bars, func(i, j int) bool { return ds.Bars[i].Time.Before(ds.Bars[j].Time) })
		out = append(out, *ds)
	}
	return out
}

func readCanonicalPartition(path string, depthLevels int) ([]bar, stats, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, stats{}, err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return nil, stats{}, err
	}
	defer gz.Close()

	r := csv.NewReader(bufio.NewReaderSize(gz, 1024*1024))
	r.ReuseRecord = true
	header, err := r.Read()
	if err != nil {
		return nil, stats{}, err
	}
	idx := canonicalHeaderIndex(header)
	required := []string{"second", "instrument", "trade_count", "trade_volume", "buy_volume", "sell_volume", "unknown_volume", "trade_open", "trade_high", "trade_low", "trade_close", "quote_updates", "bid_updates", "ask_updates", "last_bid_size", "last_ask_size", "depth_rows"}
	for _, name := range required {
		if idx[name] < 0 {
			return nil, stats{}, fmt.Errorf("missing canonical column %s", name)
		}
	}

	st := stats{File: path, TimeSource: "canonical_1s"}
	byMinute := make(map[time.Time]*bar, 1440)
	var ordered []time.Time
	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		st.Rows++
		if err != nil {
			st.BadRows++
			continue
		}
		second, err := time.Parse(time.RFC3339, get(rec, idx["second"]))
		if err != nil {
			st.BadTimestampRows++
			continue
		}
		if st.Instrument == "" {
			st.Instrument = get(rec, idx["instrument"])
		}
		updateRange(&st.EventStart, &st.EventEnd, second)
		b := getOrCreateBar(byMinute, &ordered, eventMinuteClose(second))

		tradeCount := parseInt(get(rec, idx["trade_count"]))
		if tradeCount > 0 {
			mergeCanonicalTradeSecond(b, rec, idx)
			st.TradeRows += tradeCount
			updateMaxTime(&st.LastTradeEvent, second)
			updateMaxTime(&st.LastMarketDataEvent, second)
		}
		quoteUpdates := parseInt(get(rec, idx["quote_updates"]))
		if quoteUpdates > 0 {
			b.QuoteRows += quoteUpdates
			b.BidQuotes += parseInt(get(rec, idx["bid_updates"]))
			b.AskQuotes += parseInt(get(rec, idx["ask_updates"]))
			b.QuoteBid += int64(parseFloat(get(rec, idx["last_bid_size"])))
			b.QuoteAsk += int64(parseFloat(get(rec, idx["last_ask_size"])))
			st.QuoteRows += quoteUpdates
			updateMaxTime(&st.LastMarketDataEvent, second)
		}
		depthRows := parseInt(get(rec, idx["depth_rows"]))
		if depthRows > 0 {
			b.DepthRows += depthRows
			for level := 0; level < 10; level++ {
				bid := parseInt(get(rec, idx[fmt.Sprintf("bid_p%d_volume", level)]))
				ask := parseInt(get(rec, idx[fmt.Sprintf("ask_p%d_volume", level)]))
				b.DepthBid += bid
				b.DepthAsk += ask
				if level < depthLevels {
					b.TopBid += bid
					b.TopAsk += ask
				}
			}
			st.DepthRows += depthRows
			updateMaxTime(&st.LastDepthEvent, second)
		}
	}

	bars := barsFromOrdered(ordered, byMinute)
	sort.Slice(bars, func(i, j int) bool { return bars[i].Time.Before(bars[j].Time) })
	setStatsBarRange(&st, bars)
	return bars, st, nil
}

func mergeCanonicalTradeSecond(b *bar, rec []string, idx map[string]int) {
	open := parseFloat(get(rec, idx["trade_open"]))
	high := parseFloat(get(rec, idx["trade_high"]))
	low := parseFloat(get(rec, idx["trade_low"]))
	close := parseFloat(get(rec, idx["trade_close"]))
	if b.Open == 0 {
		b.Open = open
		b.High = high
		b.Low = low
	}
	if high > b.High {
		b.High = high
	}
	if low < b.Low || b.Low == 0 {
		b.Low = low
	}
	b.Close = close
	b.Volume += parseInt(get(rec, idx["trade_volume"]))
	b.Trades += parseInt(get(rec, idx["trade_count"]))
	b.AskVolume += parseInt(get(rec, idx["buy_volume"]))
	b.BidVolume += parseInt(get(rec, idx["sell_volume"]))
	b.UnknownVol += parseInt(get(rec, idx["unknown_volume"]))
}

func canonicalHeaderIndex(header []string) map[string]int {
	idx := make(map[string]int, len(header))
	for i, name := range header {
		idx[strings.TrimSpace(name)] = i
	}
	return idx
}
