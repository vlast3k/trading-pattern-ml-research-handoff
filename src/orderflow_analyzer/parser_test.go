package main

import (
	"testing"
	"time"
)

func TestMergeBarsPrefersLiveOverReplay(t *testing.T) {
	at := time.Date(2026, 6, 1, 9, 30, 0, 0, time.UTC)
	bars := mergeBars([]bar{
		{Time: at, SourceRank: 1, Close: 101, BidVolume: 200, AskVolume: 300},
		{Time: at, SourceRank: 0, Close: 100, BidVolume: 20, AskVolume: 30},
	})

	if len(bars) != 1 {
		t.Fatalf("got %d bars, want 1", len(bars))
	}
	if bars[0].Close != 100 || bars[0].BidVolume != 20 || bars[0].AskVolume != 30 {
		t.Fatalf("live bar was not preserved: %+v", bars[0])
	}
}

func TestMergeBarsCombinesChunksFromSameSource(t *testing.T) {
	at := time.Date(2026, 6, 1, 9, 30, 0, 0, time.UTC)
	bars := mergeBars([]bar{
		{Time: at, SourceRank: 0, Open: 100, High: 101, Low: 99, Close: 100, BidVolume: 20},
		{Time: at, SourceRank: 0, High: 102, Low: 100, Close: 101, AskVolume: 30},
	})

	if len(bars) != 1 {
		t.Fatalf("got %d bars, want 1", len(bars))
	}
	if bars[0].Open != 100 || bars[0].High != 102 || bars[0].Low != 99 || bars[0].Close != 101 {
		t.Fatalf("same-source chunks were not merged: %+v", bars[0])
	}
	if bars[0].BidVolume != 20 || bars[0].AskVolume != 30 {
		t.Fatalf("same-source flow totals were not merged: %+v", bars[0])
	}
}
