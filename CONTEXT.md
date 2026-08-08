# Stock Analyze — EP Scanner

Screens US equities for Episodic Pivot setups. Agent 1 is a local technical filter that emits structured candidate lists for later news and reasoning stages.

## Language

**Episodic Pivot**:
A gap-up momentum setup driven by a fundamental shock and abnormal volume, in the Stockbee / Kullamägi sense.
_Avoid_: VCP, breakout (unless referring to a different scanner)

**Baseline Gate**:
The looser technical threshold set used to widen the daily candidate net (price, gap, relative volume).
_Avoid_: soft filter, lenient mode

**Strict Gate**:
The institutional-quality threshold set (price, market cap, liquidity, gap, relative volume, event-day dollar volume).
_Avoid_: hard filter, institutional mode (as a type name)

**Gap %**:
The percentage difference between today's regular-session open and the prior session close.
_Avoid_: daily change, close-to-close return

**RVOL10**:
Today's volume divided by the 10-day average volume.
_Avoid_: relative volume (unspecified window), RVOL50

**Event Day Dollar Volume**:
Dollars traded on the gap day (price × volume for that session).
_Avoid_: ADV, liquidity (unspecified)

**Average Daily Dollar Volume**:
Typical dollars traded per day over a lookback (here, 50 days), measuring pre-gap liquidity.
_Avoid_: average volume (shares only)

**Force Include**:
A symbol supplied via CSV that must be evaluated even if it did not appear in the screener universe.
_Avoid_: watchlist override, manual ticker

**Universe**:
The set of symbols considered in one scan run (screener results merged with force includes).
_Avoid_: watchlist, ticker list (unless meaning the CSV input file)
