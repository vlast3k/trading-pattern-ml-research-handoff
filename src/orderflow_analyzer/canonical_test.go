package main

import (
	"compress/gzip"
	"encoding/csv"
	"os"
	"path/filepath"
	"testing"
)

func TestReadCanonicalPartitionBuildsDeterministicMinute(t *testing.T) {
	path := filepath.Join(t.TempDir(), "canonical_nq_06-26_20260501_1s.csv.gz")
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	gz := gzip.NewWriter(f)
	w := csv.NewWriter(gz)
	header := []string{"second", "instrument", "trade_source", "quote_source", "depth_source", "trade_count", "trade_volume", "buy_volume", "sell_volume", "unknown_volume", "trade_open", "trade_high", "trade_low", "trade_close", "quote_updates", "bid_updates", "ask_updates", "last_bid", "last_ask", "last_bid_size", "last_ask_size", "min_spread", "max_spread", "last_spread", "depth_rows", "depth_snapshots", "last_depth_bid_total", "last_depth_ask_total", "last_depth_imbalance", "min_depth_imbalance", "max_depth_imbalance", "avg_depth_imbalance"}
	for _, side := range []string{"bid", "ask"} {
		for level := 0; level < 10; level++ {
			header = append(header, side+"_p"+string(rune('0'+level))+"_price", side+"_p"+string(rune('0'+level))+"_volume")
		}
	}
	if err := w.Write(header); err != nil {
		t.Fatal(err)
	}
	row := make([]string, len(header))
	values := map[string]string{
		"second": "2026-05-01T14:30:00Z", "instrument": "NQ 06-26",
		"trade_count": "2", "trade_volume": "5", "buy_volume": "3", "sell_volume": "2",
		"trade_open": "20000", "trade_high": "20001", "trade_low": "19999", "trade_close": "20000.5",
		"quote_updates": "4", "bid_updates": "2", "ask_updates": "2", "last_bid_size": "7", "last_ask_size": "9",
		"depth_rows": "20", "bid_p0_volume": "10", "ask_p0_volume": "8", "bid_p5_volume": "100", "ask_p5_volume": "90",
	}
	for i, name := range header {
		row[i] = values[name]
	}
	if err := w.Write(row); err != nil {
		t.Fatal(err)
	}
	w.Flush()
	if err := gz.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}

	bars, st, err := readCanonicalPartition(path, 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(bars) != 1 || st.TimeSource != "canonical_1s" {
		t.Fatalf("unexpected result bars=%d source=%s", len(bars), st.TimeSource)
	}
	b := bars[0]
	if b.Volume != 5 || b.AskVolume != 3 || b.BidVolume != 2 || b.Trades != 2 {
		t.Fatalf("unexpected trade aggregation: %+v", b)
	}
	if b.TopBid != 10 || b.TopAsk != 8 || b.DepthBid != 110 || b.DepthAsk != 98 {
		t.Fatalf("unexpected depth aggregation: %+v", b)
	}
}
