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
A symbol that must be evaluated even if it did not appear in the screener universe. Interactive Daily Run accepts a free-text paste; a cheap LLM cleans it into `(symbol, exchange)` keys (default exchange NASDAQ), surfaces rejected tokens/errors, then merges into the Universe. No CSV path.
_Avoid_: watchlist override, manual ticker, force symbols, force CSV

**Universe**:
The set of symbols considered in one scan run (screener results merged with force includes).
_Avoid_: watchlist, ticker list (unless meaning a pasted Force Include list)

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

**Daily Run**:
One stamped execution of the configured agent chain (Agent 1, optionally Agent 2 and an Analysis Method), writing Run Artifacts under a single output folder.
_Avoid_: job, batch, session (unless meaning market session)

**Auto Run**:
The wizard path that runs a full Pipeline Type (v1: Daily EP scan = Agent 1 → Catalyst → EP Rating) after gate and name prompts.
_Avoid_: quick mode, default mode

**Manual Run**:
The wizard path that chooses Gate, whether to run Catalyst, and Analysis Method before executing.
_Avoid_: step mode, custom mode

**Pipeline Type**:
The scan family selected for a Daily Run. v1 has only `daily_ep_scan`.
_Avoid_: scanner mode, workflow type

**Analysis Method**:
The post-Catalyst scoring step. v1 has only EP Rating.
_Avoid_: agent 3 (as a type name), scorer type

**Run Artifact**:
A JSON file written for one agent step of a Daily Run under `output/<date>/<time>_<name>/`, named `{name}_agentN.json`.
_Avoid_: scan dump, output blob
