package main

import (
	"time"
)

var ntLocation = time.Local
var sessionLocation = time.Local
var staleFeedThreshold = 3 * time.Minute

type rowIndex struct {
	timestamp        int
	instrument       int
	eventType        int
	marketDataType   int
	operation        int
	position         int
	price            int
	volume           int
	bid              int
	ask              int
	side             int
	bidVolume        int
	askVolume        int
	barTime          int
	barOpen          int
	barHigh          int
	barLow           int
	barClose         int
	barVolume        int
	connectionStatus int
	priceStatus      int
	lastLastTime     int
	lastBidTime      int
	lastAskTime      int
	lastDepthTime    int
	healthState      int
	healthDetail     int
	staleSeconds     int
}

type bar struct {
	Time       time.Time
	SourceRank int
	Open       float64
	High       float64
	Low        float64
	Close      float64
	Volume     int64
	BidVolume  int64
	AskVolume  int64
	Trades     int64
	QuoteRows  int64
	DepthRows  int64
	UnknownVol int64
	DepthBid   int64
	DepthAsk   int64
	TopBid     int64
	TopAsk     int64
	QuoteBid   int64
	QuoteAsk   int64
	BidQuotes  int64
	AskQuotes  int64
}

type stats struct {
	File                   string
	Instrument             string
	TimeSource             string
	Rows                   int64
	BadRows                int64
	IncompleteTailRows     int64
	BadTimestampRows       int64
	RepairedTimestampRows  int64
	TradeRows              int64
	QuoteRows              int64
	DepthRows              int64
	HealthRows             int64
	ConnectionStatusRows   int64
	EventStart             time.Time
	EventEnd               time.Time
	BarStart               time.Time
	BarEnd                 time.Time
	LastTradeEvent         time.Time
	LastBidEvent           time.Time
	LastAskEvent           time.Time
	LastDepthEvent         time.Time
	LastMarketDataEvent    time.Time
	LastHealthEvent        time.Time
	LastConnectionStatus   string
	LastPriceStatus        string
	LastHealthState        string
	LastHealthDetail       string
	LastHealthStaleSeconds float64
	MaxHealthStaleSeconds  float64
	Warnings               []string
}

type signal struct {
	Index       int
	Dir         int
	Reason      string
	Level       float64
	Delta       int64
	DeltaPct    float64
	DepthImb    float64
	WickRatio   float64
	VolumeRatio float64
	StopATR     float64
}

type result struct {
	Name      string
	Timeframe int
	Lookback  int
	Horizon   int
	Signals   int
	Wins      int
	AvgMove   float64
	AvgMFE    float64
	AvgMAE    float64
}

type trade struct {
	Instrument      string
	Timeframe       int
	Variant         string
	SignalTime      time.Time
	EntryTime       time.Time
	ExitTime        time.Time
	Dir             int
	Reason          string
	Level           float64
	Entry           float64
	Stop            float64
	Target          float64
	Exit            float64
	Outcome         string
	R               float64
	MFER            float64
	MAER            float64
	RiskPoints      float64
	Delta           int64
	DeltaPct        float64
	DepthImb        float64
	WickRatio       float64
	VolumeRatio     float64
	SignalVolume    int64
	BidVolume       int64
	AskVolume       int64
	DepthBid        int64
	DepthAsk        int64
	TopBid          int64
	TopAsk          int64
	QuoteBid        int64
	QuoteAsk        int64
	BidQuotes       int64
	AskQuotes       int64
	SignalTrades    int64
	SignalDepthRows int64
}

type simSummary struct {
	Trades        int
	Wins          int
	Losses        int
	Targets       int
	Stops         int
	Timeouts      int
	TotalR        float64
	AvgR          float64
	ProfitFactor  float64
	MaxDrawdownR  float64
	AvgRiskPoints float64
	AvgMFER       float64
	AvgMAER       float64
}

type tradeSimResult struct {
	Signals      int
	Missed       int
	Expired      int
	ChaseSkipped int
	Trades       []trade
}

type advisorProfile struct {
	Name       string
	DelayBars  int
	MissRate   float64
	ExpiryBars int
	MaxChaseR  float64
}

type advisorRow struct {
	Timeframe    int
	Variant      string
	Profile      advisorProfile
	Signals      int
	Missed       int
	Expired      int
	ChaseSkipped int
	Summary      simSummary
}

type regimePoint struct {
	Time     time.Time
	TF       int
	Method   string
	Dir      int
	Label    string
	Strength float64
}

type regimeFilterKey struct {
	RegimeTF int
	Method   string
	EntryTF  int
	Variant  string
}

type regimeFilterRow struct {
	Key      regimeFilterKey
	Base     simSummary
	Aligned  simSummary
	Against  simSummary
	Neutral  simSummary
	Missing  int
	KeptPct  float64
	AvgPower float64
}

type regimeTradeRow struct {
	RegimeTF       int
	Method         string
	RegimeTime     time.Time
	RegimeDir      int
	RegimeLabel    string
	RegimeStrength float64
	Alignment      string
	Trade          trade
}

type dayRegime struct {
	Day         string
	OpenTime    time.Time
	Complete    bool
	PriorClose  float64
	Open        float64
	GapPoints   float64
	GapPct      float64
	OR5Range    float64
	OR15Range   float64
	OR30Range   float64
	OR5Return   float64
	OR15Return  float64
	OR30Return  float64
	OR5Volume   int64
	OR15Volume  int64
	OR30Volume  int64
	OR5Bars     int
	OR15Bars    int
	OR30Bars    int
	OR30RangeZ  float64
	OR30VolumeZ float64
	GapLabel    string
	BiasLabel   string
	RangeLabel  string
	VolumeLabel string
	RegimeLabel string
}

type dollarSummary struct {
	Summary      simSummary
	Dollars      float64
	MaxDrawdown  float64
	Days         int
	PositiveDays int
	NegativeDays int
}

type dayRegimeStrategyKey struct {
	Regime    string
	Timeframe int
	Variant   string
}

type dayRegimeStrategyRow struct {
	Key     dayRegimeStrategyKey
	Summary dollarSummary
}

type dayRegimeSelectorRow struct {
	Day         string
	Regime      string
	Mode        string
	Source      string
	Timeframe   int
	Variant     string
	PriorTrades int
	PriorTotalR float64
	PriorAvgR   float64
	Summary     dollarSummary
}

type riskBudgetSummary struct {
	Budget          float64
	Trades          int
	Skipped         int
	Wins            int
	Losses          int
	Targets         int
	Stops           int
	Timeouts        int
	TotalNet        float64
	AvgNet          float64
	ProfitFactor    float64
	MaxDrawdown     float64
	TotalContracts  int
	AvgContracts    float64
	MaxContracts    int
	AvgStopRiskUsed float64
}

type apexAccountSummary struct {
	Contracts       int
	PlannedTrades   int
	TradesTaken     int
	DLLSkipped      int
	NetPnL          float64
	EndBalance      float64
	HighBalance     float64
	LowBalance      float64
	MaxDrawdown     float64
	ActiveThreshold float64
	Failed          bool
	DLLPaused       bool
	TargetHit       bool
	FailureTime     time.Time
	DLLTime         time.Time
	TargetTime      time.Time
	Status          string
}

type dataset struct {
	Key   string
	Files []string
	Bars  []bar
	Stats stats
}

type barCacheFile struct {
	Version            int
	SourcePath         string
	SourceSize         int64
	SourceModUnixNano  int64
	DepthLevels        int
	Timezone           string
	StaleThresholdNano int64
	Bars               []bar
	Stats              stats
}

type fileReadResult struct {
	Index  int
	File   string
	Bars   []bar
	Stats  stats
	Err    error
	Cached bool
}

type analysisConfig struct {
	Frames            []int
	Lookback          int
	MinWick           float64
	MinVolRatio       float64
	MinDepthImb       float64
	MACDFast          int
	MACDSlow          int
	MACDSignal        int
	RR                float64
	MaxHold           int
	TickSize          float64
	StopBufferTicks   float64
	SlippageTicks     float64
	FillMode          string
	MinRiskTicks      float64
	MaxRiskTicks      float64
	MaxEntryGapBars   int
	CleanBarsAfterGap int
	CostPoints        float64
	CommissionRT      float64
	PointValue        float64
	RiskBudgets       []float64
	ApexStartBalance  float64
	ApexProfitTarget  float64
	ApexMaxDrawdown   float64
	ApexDailyLoss     float64
	ApexMaxContracts  int
	AdvisorDelays     []int
	AdvisorMissRates  []float64
	AdvisorExpiryBars int
	AdvisorMaxChaseR  float64
	OutDir            string
	VariantFilter     string
}
