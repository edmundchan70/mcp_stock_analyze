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
A symbol evaluated even if it did not appear in the screener universe. Interactive Daily Run accepts a free-text paste; a cheap LLM cleans it into `(symbol, exchange)` keys (default exchange NASDAQ), surfaces rejected tokens/errors, then on confirm may become the sole Universe (screener skipped). Skip leaves today’s screener workflow unchanged. No CSV path.
_Avoid_: watchlist override, manual ticker, force symbols, force CSV

**Universe**:
The set of symbols considered in one scan run. Sources: screener-only (`universe_source=screener`), paste-only (`universe_source=force` when Force Include is confirmed and screener is off), or hybrid (screener + force — not used on the paste-skip-screener path).
_Avoid_: watchlist, ticker list (unless meaning a pasted Force Include list)

**Apply Gate filter**:
After metrics fetch, keep only names that pass Baseline/Strict (survivors continue). Auto Run always applies Gate after paste; Manual Run offers this vs Run all pasted.
_Avoid_: soft filter on, gate on

**Run all pasted**:
Manual-only choice after Force Include paste: fetch metrics for every pasted name, skip gate predicates, continue all enriched names to Catalyst. No Gate select prompt.
_Avoid_: ungated mode, bypass filter (as a type name)

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
The wizard path that runs a full Pipeline Type (v1: Daily EP scan = Agent 1 → Catalyst → EP Rating). Order: Pipeline → Force Include → (if paste: Gate always; if Skip: Gate) → name. Paste always applies Gate (no Run all).
_Avoid_: quick mode, default mode

**Manual Run**:
The wizard path that chooses steps before executing. Order: Force Include first → (if paste: Apply Gate filter vs Run all pasted; Gate select only if Apply) → Catalyst → Analysis Method → name. Skip Force Include keeps Gate → Catalyst → Analysis → name.
_Avoid_: step mode, custom mode

**Pipeline Type**:
The scan family selected for a Daily Run. v1 has `daily_ep_scan`, `daily_vcp_scan`, and `daily_bo_scan`.
_Avoid_: scanner mode, workflow type

**Analysis Method**:
The post-Catalyst scoring step. v1 has only EP Rating.
_Avoid_: agent 3 (as a type name), scorer type

**Run Artifact**:
A JSON file written for one agent step of a Daily Run under `output/<date>/<time>_<name>/`, named `{name}_agentN.json`.
_Avoid_: scan dump, output blob

**Run Progress**:
The live terminal timeline of a Daily Run — persistent stage lines (Agent 1, Catalyst, EP Rating), substeps, and a per-symbol ticker with remaining count. Terminal-only; not persisted to Run Artifacts.
_Avoid_: logging, debug output

---

## BO (Qullamaggie Breakout) — Daily BO scan

**BO Setup**:
A Qullamaggie breakout setup: a stock with extreme prior momentum that consolidates in a tightening base and breaks out above resistance on strong volume, price hugging its short EMA (surfing).
_Avoid_: VCP, breakout generic (without the Qullamaggie impulse/base context)

**Prior Impulse**:
The maximum % gain over a rolling 20–63 day window preceding the base. Required ≥ 30%.
_Avoid_: 52-week momentum, YTD return

**Base**:
The 10–40 day consolidation after the prior impulse peak, with VCI ≤ 0.65, narrow pre-breakout 3-day range, KDE pivot in the upper quartile, and ≥ 1 higher low.
_Avoid_: consolidation (unspecified), cup, pattern box

**ADR20**:
20-day Average Daily Range %, measured as mean((high−low)/close) over the last 20 bars. Must satisfy 4% ≤ ADR ≤ 12%.
_Avoid_: volatility (unspecified), ATR

**VCI**:
Volatility Contraction Index = ATR(5)/ATR(20), measured through base end. ≤ 0.65 required.
_Avoid_: ATR ratio, vol contraction score

**KDE Pivot**:
Gaussian KDE mode (bandwidth 3% of price) over base local peak highs, restricted to the base's upper quartile. The resistance level a breakout must clear.
_Avoid_: resistance (unspecified), prior high

**Higher Lows (S_HL)**:
Count of consecutive strictly higher swing lows into the pivot. Required S_HL ≥ 1.
_Avoid_: ascending lows (as a field name)

**Volume Signature**:
Base volume dry-up (base-end ≤ ~0.5× baseline) followed by breakout surge ≥ 1.5× baseline.
_Avoid_: volume profile, VWAP

**Surfing Distance**:
Close distance from EMA10 (%). Within ±8% required; >8% above EMA10 = overextended → 3★ clamp.
_Avoid_: extension (when meaning price above 50d SMA)

**Variant**:
`classic` (breakout above the base's KDE pivot) or `lower_base` (two-base sequence below the higher high). `lower_base` capped at 4★; only `classic` reaches 5★.
_Avoid_: subtype, pattern type

**BO Setup Rating**:
The 3–5★ pure-math rating from the 8 essential parameters + surge threshold + variant + extension cap. Deterministic, no LLM.
_Avoid_: star grade (as a field name), BO score

**BO Gate**:
Post-detection filter: setup rating ≥ 4 survives to context enrichment. Liquidity (ADV$ ≥ $10M) is always enforced.
_Avoid_: soft gate, trend filter

**BO Down-Only Caps**:
Reuses VCP cap rules — context can only cap, never boost: 5★→4★ non-leader/declining sector; 4★→3★ declining sector.
_Avoid_: upgrade rule, bonus stars

**BO Context Enrichment**:
Agent 2 reuses the VCP Tavily dual-query enrichment (`enrich_with_vcp_context`); no BO-specific agent. Runs only on 4–5★ survivors.
_Avoid_: BO news agent, custom BO enrichment

**Daily BO scan**:
`pipeline_type="daily_bo_scan"` → `_run_daily_bo()` → `{name}_agent1/2/3.json`, mirroring the VCP daily run.
_Avoid_: breakout pipeline (as a type name)

---

## Component Pipeline Editor (spec)

**Pipeline Definition**:
A named, saved graph of Components plus each Component's inspector variables, persisted independently of any Run. Reusable; the Universe (paste/sweep/Force Include) is not part of it. `graph` JSONB = `{nodes: [{id, type, position, variables}], edges: [{id, source, sourceHandle, target, targetHandle}]}`.
_Avoid_: recipe, template (unless meaning a saved graph), saved scan

**Component**:
One draggable canvas tool — Scanner (R1), Quant Filter/Gate (R2), AI Search (R3), Report (R4) — added via the floating + button. Settings panels write `node.data.variables`. Registered custom tools appear as per-entry palette items.
_Avoid_: node (unless meaning the canvas box), step, agent (unless meaning the code behind a Component)

**Component Template**:
A saved `{component_id, variables}` snapshot — a component's type + config, quick-added from the palette or applied in the inspector. Stored in the `component_templates` table.
_Avoid_: preset, snippet

**Port Stage**:
The 5 canonical row stages a Port is typed with: `symbolkey` / `scan_rows` / `filtered_rows` / `enriched_rows` / `report_rows`. A wire is legal only when the source output Port stage is in the target input Port's accept set (relaxed ordering; skip edges legal, e.g. Scanner → Report). Each Port is `required` or `optional`; an optional Port may be left unconnected.
_Avoid_: socket, handle, edge type

**Row**:
The unit of data flowing between components: `{symbol, exchange}` plus opaque extra columns. `report_rows` rows carry a numeric rating.
_Avoid_: stock object, item

**Auto-merge**:
Junctions dedupe by SymbolKey before a tool runs: one row per symbol, column union, first-wins, stable order. Fan-out copies row streams.
_Avoid_: union (unless meaning column union), join

**Soft-fail Degraded Row**:
A row whose per-symbol step throws is carried forward with an `error` marker instead of aborting the batch. Hard failures (bad params, unconnected required ports) fail the run fast.
_Avoid_: silent skip, best-effort

**Universe Node**:
The auto-seeded start node (`type:"universe"`, off the palette): one `out` Port emitting `symbolkey`, fanned out to one or more Scanners. Runtime-bound — the Definition stores the node and its edges; the Run binds the symbol source (paste / sweep / Force Include).
_Avoid_: universe placeholder (as a type name), start trigger

**ToolSpec**:
The registry protocol in `stock_analyze/tools/`: `id, name, description, phase (1-4), inputs/outputs (PortDef, 5 canonical stages only), variables (VariableDef), callable (inputs: dict[port_id, list[dict]], params: dict) -> list[dict]`. Registered via `@register("id")`; `get_tools()` serves the palette (`GET /api/tools`).
_Avoid_: plugin spec, code node

**Run Snapshot**:
The frozen graph JSON copied onto a Run when it starts (`runs.graph_snapshot`), so later edits to a Pipeline Definition never change how past Runs are interpreted.
_Avoid_: run graph, frozen params

**Lane**:
One path from Universe to a terminal component (e.g. Scanner EP → Quant → AI Search → Report). Parallel Lanes merge by SymbolKey into the lane-merge table.
_Avoid_: branch (unless meaning a fork), track, channel

**Lane-Merge Table**:
The graph-run results view: one row per symbol, with lanes, a normalized rating, and the source components. Rating precedence: `final_rating -> ep_rating -> funnel_stars -> structural_rating/setup_rating -> none`.
_Avoid_: results grid, dedupe table

**Preview Estimate**:
`POST /api/runs/preview` — runs the Universe snapshot + prefilter (1 call) and returns `{symbol_count, estimated_seconds}` so the user can confirm Polygon cost before a graph run.
_Avoid_: cost estimate, symbol count
