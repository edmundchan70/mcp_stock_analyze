# Stock Analyze — EP Scanner

Screens US equities for Episodic Pivot setups. Agent 1 is a local technical filter; Agent 2 compresses news catalysts; Agent 3 rates EP-catalyst fit (1–5) for manual chart review.

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
Typical dollars traded per day over a multi-week lookback (~50 sessions), measuring pre-gap liquidity.
_Avoid_: average volume (shares only)

**Force Include**:
A symbol supplied via CSV that must be evaluated even if it did not appear in the screener universe.
_Avoid_: watchlist override, manual ticker

**Universe**:
The set of symbols considered in one scan run (screener results merged with force includes).
_Avoid_: watchlist, ticker list (unless meaning the CSV input file)

**Catalyst**:
A clear, news-backed fundamental driver behind the gap (earnings surprise, guidance, contract, FDA, or material PR). Absence is still recorded (`catalyst_found=false`).
_Avoid_: fundamental shock (as a field name), news blurb, catalyst_text

**Catalyst Type**:
The classification of a Catalyst: `EARNINGS`, `GUIDANCE`, `CONTRACT`, `FDA`, `PR`, or `UNKNOWN`. `PR` is residual material company news outside the other types — not generic media coverage.
_Avoid_: category, news_type, event_type

**EP Rating**:
A 1–5 score of how well a name’s news/catalyst matches a textbook Episodic Pivot (catalyst substance first; technical JSON only down-caps). `5=textbook` (must look: EARNINGS/GUIDANCE shock + strong volume), `4=acceptable` (real catalyst; chart later), `3=better_not`, `2=no`, `1=bs`. Full rubric and hard caps in [glossary.md](glossary.md).
_Avoid_: Unrated, star grade, EP score (as a field name)

**EP Catalyst Match**:
True when EP Rating is 4 or 5 — the default shortlist for manual chart review.
_Avoid_: trade signal, buy flag

**Trade Opportunity Auto-Detect** (v2, deferred):
Future automated detection of pivot/base trade setup quality from OHLCV (base tightness, extension, cleared base high). Not part of v1; chart read stays manual.
_Avoid_: auto-trade, setup scorer (until v2 ships)
