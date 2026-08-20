# Glossary

Domain terms for the stock analyze scanners. Prefer these names in code, JSON keys' conceptual meaning, and docs.

| Term | Meaning |
|------|---------|
| **Episodic Pivot** | Gap-up momentum setup (Stockbee / Kullamägi) driven by a shock and abnormal volume. |
| **Baseline Gate** | Looser technical thresholds (price ≥ $1, gap ≥ 4%, RVOL10 ≥ 1.5×). |
| **Strict Gate** | Institutional thresholds (price ≥ $10, mcap $300M–$10B, 50d ADV$ ≥ $5M, gap ≥ 8%, RVOL10 ≥ 3×, event-day $ vol ≥ $20M). |
| **Gap %** | `(open − prior close) / prior close` for the regular session. |
| **RVOL10** | `volume / 10-day average volume`. |
| **Event Day Dollar Volume** | Dollars traded on the gap day. |
| **Average Daily Dollar Volume** | Typical daily dollars traded over ~50 days (pre-gap liquidity). Computed from Polygon.io OHLCV data. |
| **Force Include** | Pasted symbol list. Fast regex pre-parser for clean ticker lists (1–5 char, comma-separated); falls through to cheap LLM for messy/mixed text. The manual Universe (paste). Market-wide BO runs skip paste and use the snapshot sweep instead. |
| **Force Include Parse Result** | `ForceIncludeParseResult` dataclass (`force_include.py:37`): symbols (list[`SymbolKey`]), rejected (unparseable tokens), errors (parsing errors). |
| **Fast Parse** | Regex pre-parser in Force Include that matches clean `[A-Za-z]{1,5}` tokens without calling the LLM. Falls through to LLM on any ambiguous token. |
| **Universe** | Symbols in one scan: paste (`universe_source=force`) or market-wide sweep (`universe_source=snapshot`, BO only). |
| **Universe Source** | Origin of the symbol set for a scan: `"force"` (pasted list) or `"snapshot"` (Polygon market-wide sweep). |
| **Market Snapshot Sweep** | Polygon Snapshot universe discovery (`/v2/snapshot/locale/us/markets/stocks/tickers`): fetch all active US tickers → price/liquidity prefilter → per-symbol market-cap resolution → batch OHLCV. Snapshot alternative to paste for any family. `fetch_market_snapshot()` / `prefilter_snapshot()` / `resolve_market_caps()` (`data/polygon.py`). |
| **SymbolKey** | `(symbol: str, exchange: str)` tuple, e.g. `("AAPL", "NASDAQ")`. Unique identifier used for force-include dedup, merge, and resolution. |
| **Apply Gate filter** | Fetch metrics, apply Baseline/Strict; only survivors continue. Auto always; Manual choice after paste. |
| **Run all pasted** | Manual-only: fetch metrics for all pasted names, skip gates, continue all to Catalyst. |
| **Select** | Gate bucket parameter: `baseline`, `strict`, or `both`. Controls which surviving bucket passes to Agents 2–3. |
| **Catalyst** | News-backed fundamental driver behind the gap; absence recorded as `catalyst_found=false`. |
| **Catalyst Type** | `EARNINGS \| GUIDANCE \| CONTRACT \| FDA \| PR \| UNKNOWN` (`PR` = residual material company news). |
| **EP Rating** | 1–5 how well news matches a textbook EP. See rubric below. |
| **EP Catalyst Match** | `ep_rating >= 4` — default names to chart manually. |
| **Hard Caps** | Down-only clamps applied post-LLM in Agent 3: `UNKNOWN`/no catalyst → max 2; `PR` → max 3; `CONTRACT`/`FDA` → max 4; `rvol10 < 3` → max 4. Only `EARNINGS`/`GUIDANCE` can reach 5. |
| **Soft-fail** | Per-symbol error pattern: catch exception, produce a degraded stock entry (`catalyst_found=false`, `ep_rating=1`, error message prefixed in summary/rationale) instead of aborting the entire batch. Used in both Agent 2 and Agent 3. |
| **OHLCV Fallback** | When a force-include symbol needs metrics, gap % and RVOL10 are computed from 300 daily OHLCV bars via Polygon.io (`polygon.py`). |
| **EnrichResult** | `EnrichResult` dataclass (`tradingview.py:24`): symbol, exchange, row (dict if successful), errors. `.ok` property is `True` when row is populated. |
| **Exchange Fallback** | When primary exchange OHLCV enrichment fails, retry on NASDAQ → NYSE → AMEX → BATS → CBOE (1 attempt each). Socket is closed between exchanges to prevent stale-socket timeouts. (`tradingview.py:146`, `symbols.py:10`) |
| **Trade Opportunity Auto-Detect** | **Implemented as the EP Technical Setup Test** (`scanners/ep/setup.py:236`): pure-math OHLCV layer computing 5 boolean setup features (base, volume spike, pullback contrast, EMA 9/20/50 support, VWAP support); stock survives when ≥1 enabled feature holds. Replaces the deferred v2 item. |
| **EP Technical Setup Test** | Master toggle + 5 per-feature toggles in the Scanner filter rail ("EP technical" var group). When active, EP survivors = stocks with `features_held ≥ 1`; Baseline/Strict gates stay computed + displayed but never filter. All features off → gate semantics. (`tools/variables.py:34`, `scanners/ep/runner.py:24`) |
| **Setup Feature** | One of the 5 boolean EP features: `base_detected`, `volume_spike`, `pullback_contrast`, `ema_support`, `vwap_support`. Computed from 300 daily OHLCV bars via `score_ep_setup()`. `features_held` counts enabled held features. (`scanners/ep/setup.py`, `models/ep.py:9`) |
| **Tavily Search** | News/web search API used in Agent 2–3 for both EP (catalyst event search) and VCP (dual-query: taxonomy + leadership). Free tier: 1,000 searches/month. |
| **Tavily Dual-Query** | VCP-specific: two parallel Tavily calls per stock — Query 1 (sector/industry taxonomy, basic depth) + Query 2 (market leadership/growth catalysts, advanced depth). Executed concurrently per stock with bounded asyncio semaphore. |
| **Batch OHLCV** | `batch_get_stock_data()` in `polygon.py`: fetches 300 daily bars per stock via Polygon.io REST API with ThreadPoolExecutor concurrency, retry on rate-limit/5xx, soft-fail per symbol. Used by VCP and BO Agent 1; EP uses single-fetch `get_stock_data()`. |
| **Daily Run** | One stamped execution of the configured agent chain. |
| **Auto Run** | Wizard: Pipeline (EP/VCP/BO) → Force Include → Gate → name. Paste skips screener and always applies Gate. For EP: screener + Baseline/Strict gates. For VCP/BO: screener (Stage 2 pre-filter) + structural gates. |
| **Manual Run** | Wizard: Force Include first; paste offers Apply Gate vs Run all, then Catalyst / Analysis / name. For EP: Baseline/Strict gates. For VCP/BO: structural gates (Apply) or no gates (Run all pasted). |
| **Pipeline Type** | Scan family for a Daily Run: `daily_ep_scan` (EP pipeline), `daily_vcp_scan` (VCP pipeline), `daily_bo_scan` (BO pipeline), `daily_zhao_scan` (照妖鏡), or `daily_premarket_scan` (premarket grep). User selects via CLI subcommand or wizard first question. |
| **Analysis Method** | Post-Catalyst scoring; v1 only EP Rating. |
| **Run Artifact** | Stamped `{name}_agentN.json` under `output/<date>/<time>_<name>/`. |
| **RunConfig** | `RunConfig` dataclass (`pipeline.py:92`): all pipeline parameters — name, select, run_catalyst, analysis_method, limit, force_keys, use_screener, apply_gates, min_rating, pipeline_type, output_root. |
| **RunResult** | `RunResult` dataclass (`pipeline.py:108`): exit_code, run_dir, steps_completed, error. Returned by `run_daily()`. |
| **Run Progress** | Live terminal timeline of a Daily Run: persistent stage lines (Agent 1 / Catalyst / EP Rating), substeps, and a per-symbol ticker with remaining count. Terminal-only, not persisted to Run Artifacts. The batch OHLCV phase gets its own Rich progress bar with elapsed time and ETA, throttled every 5 fetches to avoid flicker. (`progress.py:49`) |
| **Polygon.io** | Official stock market data API (`polygon-api-client` SDK). Replaces TradingView (tvDatafeed + tradingview_screener) as the sole data source. Provides Ticker Details (symbol resolution, exchange, market cap) and daily aggregate bars (OHLCV). Polyfill for the removed Screener Pre-Filter via `passes_market_cap_gate()`. Config via `POLYGON_API_KEY` in `.env`. (`polygon.py:24`) |
| **Market Cap Gate** | Post-screener replacement: `passes_market_cap_gate()` enforces `market_cap >= MIN_MARKET_CAP` ($300M). None/missing always rejects (conservative). Applied post-symbol-resolution, pre-OHLCV-fetch in VCP/BO runners. (`scanners/vcp/gates.py:33`) |
| **Run Log** | `run.log` file written to the run directory alongside JSON artifacts. Captures all `logger` output (INFO, WARNING, ERROR) from every module in the pipeline chain (Polygon OHLCV, scanners, enrichment agents, rating agents) with timestamps and module names. Added via `FileHandler` to root logger in `_run_log()` context manager (`pipeline.py:38`), removed on completion/failure. |
| **Pre-market Data** | Minute-level aggregate bars for the current day's pre-market window (4:00 AM – 9:30 AM Eastern). Fetched via `fetch_premarket_aggs(symbol)` (`polygon.py:380`) using Polygon.io `get_aggs(timespan="minute")` with Unix timestamp millisecond boundaries. Returns DataFrame with open/high/low/close/volume. Summarized by `get_premarket_data(symbol)` returning premarket high/low/close/volume/VWAP. |
| **Premarket Window** | 4:00 AM – 9:30 AM Eastern Time. Hardcoded constants in `polygon.py:18-21`: `_PREMARKET_START_HOUR=4`, `_PREMARKET_END_HOUR=9`, `_PREMARKET_END_MINUTE=30`. Window boundaries computed daily in `_premarket_window()` (`polygon.py:372`) using ET-aware datetime arithmetic and converted to Unix millisecond timestamps for Polygon API. |

### EP Agent Pipeline

| Agent | Name | Role | File |
|-------|------|------|------|
| **Agent 1 (EP)** | Technical Filter | Polygon.io force-include merge → normalize rows → dual Baseline/Strict gate classification. With the EP Technical Setup Test active, keeps rows where `features_held ≥ 1` (gates informational). | `scanners/ep/runner.py:24` |
| **Agent 2 (EP)** | Catalyst Intelligence | Tavily news search (max_results=3) per symbol → OpenRouter LLM compresses to `CatalystSummary`. Soft-fails per symbol. | `agents/catalyst.py:78` |
| **Agent 3 (EP)** | EP Rating | Independent Tavily re-fetch (max_results=5) per symbol → OpenRouter LLM rates 1–5 → hard caps applied → sorted best→worst. | `agents/rating.py:72` |

---

## VCP (Volatility Contraction Pattern)

| Term | Meaning |
|---|---|
| **VCP** | Volatility Contraction Pattern (Mark Minervini / SEPA methodology) — a price consolidation with 2–5 progressively tighter contractions from left to right, volume drying up on each successive wave, culminating in a tight-close signature before breakout. Structural + contextual. |

### VCP Gate Pipeline (Execution Order)

| Order | Gate | Type | When Applied | On Failure | Gated? |
|---|---|---|---|---|---|
| **Gate 1** | **Market Cap Gate** — `passes_market_cap_gate()` (`gates.py:33`) | Post-screener replacement: market_cap ≥ `MIN_MARKET_CAP` ($300M). Resolved via Polygon Ticker Details. None/missing always rejects. | Post-symbol-resolution, pre-OHLCV-fetch. **Always enforced** — replaces old TradingView screener pre-filter. | Silently skipped (no entry in any bucket). | Always |
| **Gate 2** | **Liquidity Gate** — `passes_liquidity_gate()` (`gates.py:29`) | Hard pre-requisite: 60d ADV$ ≥ `MIN_ADV_DOLLAR` ($10M) computed pure-math from OHLCV DataFrame (`avg_volume × close` over last 60 bars). | Post-OHLCV-fetch, pre-VCP-scoring. **Always enforced** — even in "Run all pasted" mode. | Silently skipped (no entry in any bucket). Protects against force-included illiquid stocks. | Always |
| **Gate 3** | **Stage 2 Trend Template** — `passes_stage2_gate()` (`gates.py:43`) | RS ≥ 70 AND `is_stage2=True` (price > 50/200 SMA, rising 200 SMA). | Post-VCP-scoring, only if `apply_gates=True`. | Downgraded to 3★ but still appears in 3★ bucket for visibility. | `apply_gates` |
| **Gate 4** | **VCP Structural Gate** — `passes_vcp_gate()` (`gates.py:48`) | `structural_rating ≥ 4`. Only 4–5★ survivors pass to Agent 2/3 (context enrichment + final report). | Post-detection classification, only if `apply_gates=True`. | Stays in 3★ bucket; no Tavily enrichment, no final report. | `apply_gates` |

### Force Include to OHLCV Resolution Flow (Polygon.io)

When a user pastes symbols, the pipeline resolves them via Polygon.io:

| Step | API | What It Does | Per-Symbol? | File |
|---|---|---|---|---|
| **1. Ticker Details** (`resolve_force_symbol()`) | `polygon-api-client` (REST) | `get_ticker_details(symbol)` — resolve symbol to exchange, market cap, name, description. | Yes — one call per symbol. | `polygon.py:198` |
| **2. OHLCV Fetch** (`get_stock_data()` / `batch_get_stock_data()`) | `polygon-api-client` (REST) | For each symbol: `get_aggs(symbol, daily, n=300)` → DataFrame with open/high/low/close/volume. `batch_get_stock_data()` uses ThreadPoolExecutor with retry on rate-limit/5xx. | Yes — one `get_aggs()` per symbol. | `polygon.py:82,148` |

**Key insight**: Pasted symbols are resolved directly via Polygon.io Ticker Details → OHLCV. No TradingView screener or WebSocket layer. Market cap gate is enforced post-resolution.

### VCP Error Handling

| Scenario | Mechanism | User Impact |
|---|---|---|
| **Polygon symbol resolution fails** | `resolve_force_symbol()` returns `None` → appended to `_failed_force` list, persisted in agent1 JSON. | Terminal prints warning: "Force-include symbols could not be resolved via Polygon". Symbol excluded from pipeline. |
| **Polygon Ticker Details API fails** | `resolve_force_symbol()` catches exception, returns `None`. | Same as resolution failure — symbol excluded from pipeline. |
| **Batch Polygon OHLCV fails for one symbol** | `batch_get_stock_data()` retries on rate-limit/5xx, stores `None` if all retries exhausted. `run_vcp_scan()` / `run_bo_scan()` skips `None` entries. | Symbol silently excluded from VCP/BO scoring. |
| **Liquidity gate rejects a symbol** | `passes_liquidity_gate()` returns `False` → `continue` in `run_vcp_scan()`. | Symbol silently excluded (no rating, no bucket). |
| **Stage 2 Trend Template** | Minervini's uptrend checklist: price > 50-day SMA > 150-day SMA > 200-day SMA; 200-day SMA is rising; stock near 52-week high. Required for any VCP to qualify above 3★. |
| **RS Line** | Relative Strength line: `stock_close / spy_close` computed daily. RS ≥ 85 for 5★, RS ≥ 70 for 4★. Computed pure-math from OHLCV, not via TradingView screener. |
| **52-Week High Proximity** | `current_price / 52W_high`. Within 0–10% for 5★, within 10–20% for 4★, >25% below = 3★. |
| **Contraction** | A single VCP wave: high pivot → low pivot with measured depth, dollar range, and average volume. |
| **Contraction Count (k)** | Number of VCP waves; 3–4 for 5★, 2 or 5 for 4★, 1 or >5 for 3★. |
| **Trough Symmetry (Li)** | Each successive low is strictly higher: `L_i > L_{i-1}` for 5★. Lower low detected = 3★ (breakdown). |
| **Peak Symmetry (Hi)** | Highs stay flat or rising: `H_i ≥ 0.99·H_{i-1}` for 5★. Descending triangle (`H_i < 0.95·H_{i-1}`) = 3★. |
| **Dollar Range Contraction (ΔRi)** | Each contraction's high-low range strictly shrinks: `ΔR_i ≤ 0.75·ΔR_{i-1}` for 5★. Expanding range = 3★. |
| **Depth Percentage (Di)** | Contraction depth monotonically falls, e.g. 15%→8%→3% for 5★. Expanding depth = 3★. |
| **Tight Closes Signature** | 2–4 days of very narrow daily ranges at the final contraction: span ≤ 1.25%, CV ≤ 0.8% for 5★. Absent = 3★. |
| **Volume Decay Rate** | Per-wave average volume drop: ≥ 15–20% per wave for 5★. Pivot day volume ≤ 40% of SMA20. Expanding volume = 3★. |
| **Time Contraction (Ti)** | Each contraction takes similar or less time: `T_1 > T_2 > T_3` for 5★. "Eternal base" (`T_k ≫ T_1`) = 3★. |
| **VCP Structural Rating** | 1–5★ rating computed pure-math from 9 parameters. Deterministic, no LLM. 3★ and below = disqualified. |
| **VCP Stage 2 Gate** | Pre-VCP filter: RS < 70 or non-Stage-2 → discard before running VCP pattern detection. Applied at Agent 1. |
| **VCP Liquidity Gate** | Hard pre-requisite: 60d ADV$ >= $10M computed from OHLCV (volume × close) after fetch. Always enforced at Agent 1 before VCP scoring — even in "Run all pasted" mode. Rejects illiquid stocks (e.g., sub-1,000-share vol) that would otherwise pass pattern detection. Uses the same $10M threshold as the TradingView screener pre-filter. `gates.py:29` |
| **VCP Structural Gate** | Post-detection classification: 3★ discarded, 4–5★ pass to enrichment (Agent 2). Only 4–5★ get Tavily context. |
| **VCP Context Enrichment** | Tavily dual-query (taxonomy + leadership) + LLM parse into `VcpContextEnrichment`. Only runs on 4–5★ survivors. Fires on final survivors from gate, or on all pasted if Run All (no gate). |
| **Structural Taxonomy Vector** | Tavily Query 1: `"{symbol} {company_name} stock sector industry classification top competitors"`. `topic=finance`, `search_depth=basic`, `max_results=5`. |
| **Market Leadership Vector** | Tavily Query 2: `"{symbol} {company_name} market leader competitors market share growth drivers key catalysts"`. `topic=news`, `search_depth=advanced`, `time_range=month`. |
| **Industry Group Strength Flag** | `HOT_SECTOR \| NEUTRAL \| DECLINING_GROUP` — LLM classified from Tavily results. |
| **Niche Leader** | Boolean: company ranks top 1–3 in market share, revenue growth, or tech leadership within its specific sub-industry. |
| **VCP Down-Only Caps** | Context can only cap structural rating, never boost. Rules: 5★ → 4★ if non-leader or declining sector. 4★ → 3★ if declining sector. 3★ stays 3★ regardless of context. |
| **VCP Batch OHLCV Fetch** | `batch_get_stock_data()` in `tradingview_data.py`: persistent WebSocket across 250 symbols, refresh every 50, 300ms inter-fetch delay, soft-fails per symbol. ~7.5 min for 250 stocks. |
| **VCP Auto Run** | Wizard: Pipeline=VCP → Screener (Stage 2 pre-filter) → Force Include (optional paste) → `apply_gates=True` → run_daily. Mirror of EP Auto. |
| **VCP Manual — Apply Gate** | Wizard: Pipeline=VCP → Force Include paste → "Apply Gate" → fetch OHLCV → Stage 2 + VCP gate → only survivors to enrichment. |
| **VCP Manual — Run All Pasted** | Wizard: Pipeline=VCP → Force Include paste → "Run all pasted" → fetch OHLCV → skip gates → ALL pasted continue to enrichment. |

### VCP Agent Pipeline

| Agent | Name | Role | File |
|-------|------|------|------|
| **Agent 1 (VCP)** | VCP Structural Scanner | Polygon force-include merge → batch OHLCV fetch → SPY RS line → Market cap gate (≥ $300M) → Liquidity gate (ADV$ ≥ $10M) → Stage 2 gate → VCP pattern detection (pure math, 9 params) → 1–5★ classification into buckets. | `scanners/vcp/runner.py:72` |
| **Agent 2 (VCP)** | VCP Context Enrichment | Tavily dual-query per symbol (taxonomy + leadership, parallel) → OpenRouter LLM parses into `VcpContextEnrichment` → applies down-only caps. Only 4–5★ survivors (or all pasted if Run All). | `agents/enrichment.py:164` |
| **Agent 3 (VCP)** | VCP Final Report | Merge structural rating + context enrichment → apply cap rules → sort final_rating desc → write ranked artifact. | `pipeline.py:353` |

### VCP Structural Rating Rubric (v1)

| Parameter | 5★ (Textbook / High-Conviction) | 4★ (Strong / Tradable) | 3★ (Sub-standard / Disqualified) |
|---|---|---|---|
| **Stage 2 Trend** | Price > 50/150/200 SMA; Rising 200 SMA; RS ≥ 85 | Price > 50/200 SMA; Rising 200 SMA; RS ≥ 70 | Non-Stage 2; Price < 200 SMA; Declining 200 SMA; RS < 70 |
| **52W High Proximity** | Within 0–10% of 52W/ATH | Within 10–20% of 52W High | >25% below 52W High |
| **Contraction Count (k)** | 3–4 waves | 2 or 5 waves | 1 wave or >5 waves |
| **Trough Symmetry (Li)** | Strictly Higher Lows | Higher Lows | Lower Low Detected |
| **Peak Symmetry (Hi)** | Flat or Rising Highs (`≥0.99·H_{i-1}`) | Minor Slope (`≥0.97·H_{i-1}`) | Descending Triangle (`<0.95·H_{i-1}`) |
| **Dollar Range (ΔRi)** | Monotonic Fall (`≤0.75·ΔR_{i-1}`) | General Fall (≥80% of base) | Expanding Range |
| **Depth % (Di)** | Monotonic Fall (15%→8%→3%) | Monotonic Fall (20%→10%) | Expanding Depth |
| **Tight Closes** | Mandatory: 2–4 days, Span ≤1.25%, CV ≤0.8% | Moderate: 2–3 days, Span ≤2.0%, CV ≤1.5% | Absent: Span >2.5%, high variance |
| **Volume Decay** | ≥15–20% drop per wave; Pivot Vol ≤40% SMA20 | 10–15% drop per wave; Pivot Vol ≤65% SMA20 | Expanding volume; Pivot Vol > SMA20 |
| **Time Contraction** | Strictly Contracting (T1>T2>T3) | Bounded (Ti ≤1.2·T_{i-1}) | Eternal Base (Tk ≫ T1) |

### VCP Down-Only Cap Rules

| Structural Rating | Context Condition | Final Rating |
|---|---|---|
| 5★ | `is_category_leader=true` AND `industry_group_strength_flag=HOT_SECTOR` | 5★ (no cap) |
| 5★ | `is_category_leader=true` AND `industry_group_strength_flag=NEUTRAL` | 5★ (no cap — leader still tradeable) |
| 5★ | `is_category_leader=false` OR `industry_group_strength_flag=DECLINING_GROUP` | 4★ (cap) |
| 4★ | `industry_group_strength_flag=DECLINING_GROUP` | 3★ (cap — soft setup in weak sector) |
| 4★ | `HOT_SECTOR` or `NEUTRAL` | 4★ (no cap) |
| 3★ | Any | 3★ (already disqualified) |

---

## BO (Qullamaggie Breakout)

| Term | Meaning |
|---|---|
| **BO** | Qullamaggie Breakout setup — a stock with extreme prior momentum (prior impulse ≥ 30% over 20–63 days), consolidating in a tightening base (5–40 days), then breaking out above resistance (KDE pivot) with a volume surge (≥ 1.5× baseline) while hugging its EMA10. Structural + contextual. |
| **Prior Impulse** | Max % gain over a rolling 20–63 day window. Required ≥ 30%. `prior_impulse(closes)` (`metrics.py:43`). |
| **ADR20** | 20-day Average Daily Range % = mean((high−low)/close) over last 20 bars. Must satisfy 4% ≤ ADR ≤ 12% envelope — below = sluggish, above = excessive spread/gap risk. `avg_daily_range_pct()` (`metrics.py:70`), `passes_adr_envelope()` (`gates.py:13`). |
| **Base** | The consolidation after the impulse peak, measured 5–40 trading days, with VCI ≤ 0.65, a narrow pre-breakout 3-day range, a KDE pivot in the upper quartile, and S_HL ≥ 1 higher lows. `detect_bases()` (`metrics.py:338`). |
| **VCI** | Volatility Contraction Index = ATR_short(5) / ATR_medium(20), measured through the base end. Must be ≤ 0.65. `vci_atr()` (`metrics.py:94`). |
| **KDE Pivot** | Gaussian KDE (bandwidth = 3% of current price) over local peak highs (2-day radius) of the base window; pivot = global KDE mode located in the upper quartile of the base's high-low range. `kde_pivot()` (`metrics.py:157`). |
| **Higher Lows (S_HL)** | Count of consecutive strictly higher swing lows (2-day radius) leading into the pivot. Required S_HL ≥ 1. `higher_lows()` (`metrics.py:210`). |
| **Volume Signature** | Dual condition (UT-06): base-end volume must dry up to ≤ ~0.5× pre-base baseline **and** the breakout bar must surge ≥ 1.5× baseline. Both enforced as the volume essential in `score_bo_setup()`. `volume_signature()` (`metrics.py:255`). |
| **BO 9 Essentials** | The 9 boolean flags persisted on `BoSetupRating` that must all be true for >3★: `prior_impulse`, `adr20`, `base_duration`, `vci`, `ma_stack`, `pivot_kde`, `higher_lows`, `dryup`, `volume_surge`. Canonical order defined in `ESSENTIAL_KEYS` (`metrics.py:41`). |
| **BO Near-Miss** | A 3★ `BoSetupRating` that passed ≥ 7 of 9 essentials and is NOT overextended. Persisted as `BoNearMiss` in `BoScanBucket.near_miss`, computed only when `apply_gates=True`. Sorted closest-first (`failed_count` asc, `rs_rating` desc, `None` last). Printed as a table on the no-4-5★ survivor short-circuit. Model: `models/bo.py:BoNearMiss`. |
| **Surfing Distance** | Close distance from EMA10 (%). Must be within ±8% — >8% above EMA10 = overextended → clamp to 3★. `ma_stack()` (`metrics.py:116`). |
| **MA Stack** | EMA10 > EMA20, positive EMA50 slope, and close within 8% of EMA10. `ma_stack()["aligned"]`. |
| **Extension Cap** | EC-01: close > 8% above EMA10 → `extension=True`, setup clamped to 3★. SMA50 distance reported separately as `sma50_extension_pct` (secondary field, never a gate). |
| **Breakout** | A bar after base.end where close > pivot AND volume surge ≥ 1.5× baseline. `detect_breakout()` (`metrics.py:372`). |
| **Variant** | `classic` (breakout above base's KDE pivot) or `lower_base` (two-base sequence: base A higher high → shallower base B below A's high → close above B's high but below A's high). `lower_base` capped at 4★; only `classic` reaches 5★. `classify_variant()` (`metrics.py:410`). |
| **BO Setup Rating** | 3–5★ pure-math rating from 9 essential checks (incl. volume signature = dry-up ≤ 0.5× then surge ≥ 1.5×) + surge-threshold tiers + variant + extension cap. Deterministic, no LLM. `score_bo_setup()` (`metrics.py:432`). |
| **BO Liquidity Gate** | Reuses VCP `passes_liquidity_gate()` / `MIN_ADV_DOLLAR` ($10M) — always enforced post-OHLCV-fetch. |
| **BO Gate** | Post-detection gate (legacy): `rating ≥ 4` survives. Replaced by BO Funnel Gate. `passes_bo_gate()` (`gates.py:18`). |
| **BO Funnel Gate** | 5-gate pipeline (G1 prior_impulse → G2 20d ADV$ → G3 EMA10 proximity + rising → G4 base duration → G5 dry-up scoring-only) + Q_base scoring ≥ 60 floor. Replaces the single `rating >= 4` structural gate for BO survivors. `apply_funnel()` (`watchlist.py:118`). |
| **BO Funnel Profile** | One of `best` (ADV $50M / EMA 5% / Base 40d), `moderate-lose` (ADV $50M / EMA 8% / Base 40d), or `widen` (ADV $30M / EMA 8% / Base 40d). All disable dry-up as a hard gate (scoring-only). `WATCHLIST_PROFILES` (`watchlist.py:19`). |
| **Q_base** | Composite quality score (max 100) from 6 parameters: VCI, higher lows count, tightness, prior impulse %, volume dry-up ratio, and EMA10 surfing distance. Drives funnel star tier: 90→5★, 75→4★, 60→3★. `compute_q_base()` (`watchlist.py:54`). |
| **Tradable Count** | Survivors with `funnel_stars ≥ 3` (Q_base ≥ 60). Triggers gap-options prompt when < 5. `tradable_count()` (`watchlist.py:178`). |
| **Gap-Options Prompt** | Interactive (wizard + CLI TTY) free-loop prompt shown when tradable survivors < 5. User picks best/moderate-lose/widen repeatedly; "Keep what I have" proceeds with current survivors. CLI `--profile` flag skips the prompt. |
| **Tightness** | Last-bar daily range as a fraction of ADR20: `(high[-1] − low[-1]) / close[-1] × 100 / ADR20`. Low tightness contributes positively to Q_base. Computed in `run_bo_scan()` (`runner.py:173`). |
| **BO Down-Only Caps** | Reuses VCP `apply_vcp_caps()` — applied to `funnel_stars` (not structural `rating`) when funnel stars > 0. 5★→4★ if non-leader or declining sector; 4★→3★ if declining sector; 3★ stays 3★. `build_bo_rated_stock()` (`gates.py:28`). |
| **BO Context Enrichment** | Agent 2 — reuses VCP Tavily dual-query enrichment as-is (`enrich_with_vcp_context`); no BO-specific agent. |
| **BO Batch OHLCV Fetch** | Same `batch_get_stock_data()` as VCP (300 daily bars, Polygon.io REST API). `run_bo_scan()` (`runner.py:81`). |
| **BO Auto Run** | Wizard: Pipeline=Qullamaggie BO (Classic) → Force Include → Funnel gate (best) → gap-options prompt if tradable < 5 → enrichment. |
| **BO Manual — Apply Gate** | Wizard: Pipeline=Qullamaggie BO (Classic) → Force Include paste → "Apply Gate" → Funnel gate → gap-options prompt → survivors to enrichment. |
| **BO Manual — Run All Pasted** | Wizard: Pipeline=Qullamaggie BO (Classic) → Force Include paste → "Run all pasted" → skip gates → ALL pasted continue to enrichment. |

### BO Agent Pipeline

| Agent | Name | Role | File |
|-------|------|------|------|
| **Agent 1 (BO)** | BO Structural Scanner | Polygon force-include merge (paste) or snapshot sweep → batch OHLCV fetch → SPY RS line → Market cap gate (≥ $300M) → Liquidity gate (ADV$ ≥ $10M) → BO setup detection (prior impulse, ADR envelope, VCI, MA stack, KDE pivot, higher lows, volume signature = dry-up + surge) → 3–5★ classification into buckets. | `scanners/bo/runner.py:81` |
| **Agent 2 (BO)** | BO Context Enrichment | Reuses VCP Tavily dual-query enrichment (`enrich_with_vcp_context`). Only 4–5★ survivors (or all pasted if Run All). | `agents/enrichment.py:246` |
| **Agent 3 (BO)** | BO Final Report | Merge setup rating + context enrichment → apply down-only caps (reuse `apply_vcp_caps`) → sort final_rating desc → write ranked artifact. | `pipeline.py:execute_bo_enrichment` |

### BO Setup Rating Rubric (v1)

| Parameter | 5★ (Textbook) | 4★ (Strong) | 3★ (Sub-standard) |
|---|---|---|---|
| **Prior Impulse** | ≥ 30% over 20–63d | ≥ 30% | < 30% |
| **ADR20** | 4%–12% | 4%–12% | outside envelope |
| **Base Duration** | 5–40d (optimal 15–25) | 5–40d | > 40d (stale) or absent |
| **VCI** | ≤ 0.65 | ≤ 0.65 | > 0.65 |
| **MA Stack / Surfing** | EMA10>EMA20, EMA50 slope > 0, close within 8% of EMA10 | aligned | not aligned or >8% extended |
| **KDE Pivot** | in base upper quartile | in base upper quartile | absent |
| **Higher Lows** | S_HL ≥ 1 | S_HL ≥ 1 | S_HL = 0 |
| **Volume Surge** | ≥ 3.0× (classic) | ≥ 2.0× (classic) / ≥ 1.5× (lower_base) | < 1.5× (fakeout) |
| **Variant** | classic | classic or lower_base (cap 4★) | none |

### BO Down-Only Cap Rules (reuse VCP)

| Setup Rating | Context Condition | Final Rating |
|---|---|---|
| 5★ | `is_category_leader=true` AND flag ≠ DECLINING_GROUP | 5★ (no cap) |
| 5★ | `is_category_leader=false` OR `industry_group_strength_flag=DECLINING_GROUP` | 4★ (cap) |
| 4★ | `industry_group_strength_flag=DECLINING_GROUP` | 3★ (cap) |
| 4★ | HOT_SECTOR or NEUTRAL | 4★ (no cap) |
| 3★ | Any | 3★ (already disqualified) |

---

## EP Rating rubric (v1)

| Stars | Label | Meaning |
|------:|--------|---------|
| 5 | `textbook` | Must look — clear **EARNINGS/GUIDANCE** shock + strong volume (`rvol10` typically ≫ 3×). |
| 4 | `acceptable` | Worth charting if setup looks great — real fundamental catalyst (earnings/guidance/strong contract/FDA). |
| 3 | `better_not` | Catalyst exists but weak/vague for a classic EP (e.g. thin PR). |
| 2 | `no` | News does not support an EP. |
| 1 | `bs` | No credible catalyst / garbage / soft-fail. |

**Hard caps (code, down-only):** `UNKNOWN`/`catalyst_found=false` → max 2; `rvol10 < 3` → max 4; `PR` → max 3; `CONTRACT`/`FDA` → max 4; soft-fail → 1. **5★ reserved for EARNINGS/GUIDANCE.**

See [CONTEXT.md](CONTEXT.md) for full definitions and avoided synonyms.

---

## Full-stack dashboard (Next.js + FastAPI)

| Term | Meaning |
|------|---------|
| **Run (DB record)** | A persisted scan execution in the `runs` table: `id`, `name`, `pipeline_type`, `status`, `params` (JSONB), `counts` (JSONB), `error`, `started_at`, `finished_at`. Status lifecycle: `queued → running → succeeded \| failed \| cancelled`. Managed by `Repo` (`server/app/db.py`). |
| **Run Artifacts (DB)** | The `run_artifacts` table: one JSONB `payload` per `(run_id, stage)` where stage ∈ `meta` \| `agent1` \| `agent2` \| `agent3`. Upserted from `read_artifacts()` after `run_daily()` finishes (`server/app/jobs.py`). |
| **EventReporter** | `RunProgress` duck-type adapter (`server/app/reporter.py`) that marshals `stage` / `stage_done` / `fail` / `begin_ticker` / `ticker` / `end_ticker` / `console.print` calls onto an asyncio.Queue via `loop.call_soon_threadsafe` (pipeline runs in a worker thread). |
| **JobManager** | Registry of in-flight runs: one event queue + one `asyncio.Task` per run id (`server/app/jobs.py:JobManager`). |
| **SSE Progress** | `GET /api/runs/{id}/events` streams `progress` events (each with a `type` field = reporter event) and a terminal `done`/`failed` event; replays a terminal event from the DB if the run already finished. |
| **Scan Job** | `run_scan_job()`: builds `RunConfig` from the request body (sharing `parse_force_include_text` with the CLI), runs `run_daily()` via `asyncio.to_thread`, then reads artifacts back and persists to Postgres. |

---

## Component Pipeline Editor (spec)

| Term | Meaning |
|------|---------|
| **Pipeline Definition** | A named, saved graph of Components + per-Component inspector variables, persisted independently of any Run. Universe (paste/sweep/Force Include) is per-Run, not part of the Definition. `graph` JSONB = `{nodes: [{id, type, position, variables}], edges: [{id, source, sourceHandle, target, targetHandle}]}`. |
| **Component** | One draggable canvas tool from the palette: Scanner (R1), Quant Filter/Gate (R2), AI Search (R3), Report (R4). Added via the floating **+** button. Settings panels write `node.data.variables`. Registered custom tools surface as per-entry palette items. |
| **Component Template** | A saved `{component_id, variables}` snapshot — a component's config, quick-added from the palette or applied in the inspector. Stored in the `component_templates` table. |
| **Graph Template** | A saved graph (`nodes` + `edges` + variables); stored as a Pipeline Definition. Saved/loaded in the editor header. |
| **Row** | The unit of data flowing between components: `{symbol, exchange}` plus opaque extra columns. `report_rows` rows must carry a numeric rating. |
| **Port Stage** | The 5 canonical row stages a Port is typed with: `symbolkey` / `scan_rows` / `filtered_rows` / `enriched_rows` / `report_rows`. Wiring legality = port-stage assignability only (relaxed ordering; skip edges legal, e.g. Scanner → Report). |
| **Input Accepts** | The assignability matrix: `filtered_rows` accepts `scan_rows\|filtered_rows`; `enriched_rows` accepts `scan_rows\|filtered_rows\|enriched_rows`; `report_rows` accepts `scan_rows\|filtered_rows\|enriched_rows`. Canonical source: `INPUT_ACCEPTS` in `stock_analyze/tools/protocol.py` (server) mirrored by `web/lib/graph.ts` (canvas `isValidConnection`). |
| **Auto-merge** | Junctions dedupe by SymbolKey before a tool runs: one row per symbol, column union, first-wins, stable order. Fan-out copies row streams. |
| **Soft-fail Degraded Row** | A row whose per-symbol step throws is carried forward with an `error` marker instead of aborting the batch. Hard failures (bad params, unconnected required ports) fail the run fast. |
| **Universe Node** | The auto-seeded start node (`type:"universe"`, off the palette): one `out` Port emitting `symbolkey`, fanned out to Scanners. Runtime-bound — the Definition stores the node + edges, the Run binds the symbol source (paste/sweep/Force Include). |
| **ToolSpec** | The registry protocol in `stock_analyze/tools/`: `id, name, description, phase (1-4), inputs/outputs (PortDef, 5 canonical stages only), variables (VariableDef), callable (inputs: dict[port_id, list[dict]], params: dict) -> list[dict]`. Registered via `@register("id")`; `get_tools()` serves the palette (`GET /api/tools`). |
| **Run Snapshot** | Frozen graph JSON copied onto a Run at start (`runs.graph_snapshot`); edits to the Definition do not alter historical Runs. |
| **Lane** | One path from Universe to a terminal component; parallel lanes merge by SymbolKey into the lane-merge table. |
| **Lane-Merge Table** | The graph-run results view: one row per symbol, with lanes, a normalized rating, and the source components. Rating precedence: `final_rating -> ep_rating -> funnel_stars -> structural_rating/setup_rating -> none`. |
| **Preview Estimate** | `POST /api/runs/preview` — runs the Universe snapshot + prefilter (1 call) and returns `{symbol_count, estimated_seconds}` so the user can confirm Polygon cost before a graph run. `estimated_seconds = ceil(symbol_count × calls_per_symbol / effective_calls_per_min)`. |
| **Scanner Family** | The Scanner's `family` variable (`ep`/`vcp`/`bo`/`zhao`/`premarket`/`custom`, renamed from the stub's `ep_gap`) swaps which threshold groups the inspector shows. |
| **Daily Preset Definition** | One of three full-chain canvas definitions seeded into `pipeline_definitions` at server boot by `server/app/seed.py`: `Daily VCP Scan`, `Daily BO Scan`, `Daily EP Scan` (each `Universe → Scanner → AI Search → Report`). Seed-if-absent **by name** (idempotent, self-healing — user edits survive, deletions resurrect). The universe-source default is carried as `graph.defaults.universe_source` (`"snapshot"` for BO, `"paste"` for VCP/EP); the walker ignores this extra top-level key. |

---

## Runtime Control (graph runs)

| Term | Meaning |
|------|---------|
| **Runtime Control** | Interactive, in-flight control of a component graph run: skip / pause / resume / cancel, plus an AI-Search confirmation gate. Scope: graph runs only (not legacy `run_daily`). |
| **RunControl** | Thread-safe per-run control object (`server/app/control.py:21`) owned by `JobManager._controls`. Guards a skip set, pause/cancel `threading.Event`s, and confirm-gate state with `threading.Lock`. |
| **RunCancelled** | Cooperative cancel exception (`stock_analyze/tools/control.py:20`) raised at the next checkpoint once cancel is armed; the job maps it to `cancelled` status. |
| **Checkpoint** | A blocking callable the search agents call at per-symbol boundaries (`RunControl.checkpoint`). Returns immediately while running, freezes (drain-then-freeze) while paused, raises `RunCancelled` once cancelled. |
| **Skip (pass-through)** | Pre-emptive node skip: the node's input rows flow through unchanged and `NodeResult.status = skipped`; Report still produces a table. Skip-after-started is a no-op. |
| **Pause / Resume** | Pause freezes the walker at the next checkpoint (between nodes or at the next per-symbol boundary; in-flight ≤5 Tavily/LLM calls drain). Resume clears the flag. |
| **Cancel** | Graceful: stop scheduling new work at the next checkpoint, mark the run `cancelled`, persist partial artifacts. Also resolves a pending confirmation gate. |
| **Confirmation Gate** | Pre-AI-Search block: when the `search` node's input rows exceed `confirm_threshold` (default 50, 0 = off), the run blocks and emits `confirm_needed`; user picks `proceed` / `skip` / `cancel`. Armed skip suppresses the gate (skip-wins). |
| **`confirm_threshold`** | AI-Search `SEARCH_VARS` variable (`stock_analyze/tools/variables.py:119`): "Confirm above N symbols", default 50. |
| **Awaiting Confirmation** | Persistent run state (dashboard + run detail) while a node is blocked on the gate; cancelable there. Exposed via `RunControl.pending_confirmation()` and `_attach_control_state`. |
| **`__control_id__`** | JSON-safe opaque token injected into each node's `params` by `run_graph`; `_search_callable` recovers the `RunControl` via `checkpoint_for` to populate the agents' `checkpoint` kwarg. |
| **Interrupted-Run Reconciliation** | On server startup, `Repo.mark_interrupted_runs()` (`server/app/db.py:137`) marks orphaned `queued`/`running` rows `failed` with error `server restarted — run interrupted`. |
| **Control Endpoint** | `POST /api/runs/{id}/control` (`server/app/routes/runs.py:199`) with actions `skip|pause|resume|cancel|confirm` (confirm carries `decision: proceed|skip|cancel` + `node_id`). |
| **`node:<id>` Artifact** | Per-node artifact persisted on graph-run completion/cancel: `{tool_id, status, output_rows, errors, dropped, duration_ms, error}` (`server/app/jobs.py:145`). Used to reconstruct node progress for late SSE subscribers. |

---

## Guided 5-Phase Scan Flow (UI)

| Term | Meaning |
|------|---------|
| **Guided 5-Phase Scan Flow** | The linear frontend workflow replacing the component-graph editor (`web/app/flow/page.tsx`): **1 Universe → 2 Scanner → 3 Pattern → 4 AI Search → 5 Report**. Reuses the existing pipeline/SSE/preview machinery unchanged. |
| **Flow Draft** | The client-side persisted workflow state (`web/lib/flow.ts`, `FlowState`), stored under `stock-scan-flow-v1` in `localStorage` for reload recovery. Includes universe config, family, scanner vars, scan/search run ids, and extracted rows. |
| **Phase Stepper** | Persistent top nav (`PhaseStepper.tsx`). A phase is **locked** (`phaseLocked`) when its prerequisite data is missing and shows ✓ (`phaseDone`) when its work is complete: Scanner needs a universe, Pattern/AI Search need scan rows, Report needs ranked rows. |
| **Starter Preset** | A seeded `pipeline_definitions` row matching `/^Daily (VCP\|BO\|EP) Scan$/`, surfaced in `PresetManager.tsx` as a family-only one-click scanner config. "My settings" are saved `component_templates` rows (full variable snapshots). zhao/premarket starters (`照妖鏡 realtime`, `照妖鏡 daily`, `Premarket grep`) are builtin frontend presets (`BUILTIN_STARTERS`) until seeded definitions exist. |
| **Pattern Evidence** | Chart evidence fetched via `POST /api/ohlcv` (`server/app/routes/symbols.py`, wrapping `batch_get_stock_data`) and rendered with `lightweight-charts` in `ChartCard.tsx`. Overlays (`patternOverlay` in `web/lib/flow.ts`) anchor base high/low, KDE pivot, breakout bar, and gap day from scan-row fields. Evidence-only: no keep/drop gate, all survivors flow to AI Search. |
| **Pattern Anchor Fields** | 0-based bar indices on scanner rows that drive chart overlays: `base_start_idx` / `base_end_idx` / `breakout_idx` (BO, from `BoSetupRating`), plus price anchors `base_high` / `base_low` / `pivot` / `prior_close`. |
| **Activity Feed** | The persistent "what's happening" stream (`ActivityFeed.tsx` + `useRunEvents` in `web/lib/runEvents.ts`): timestamped, color-coded SSE events from `subscribeToRunEvents`, auto-scrolling; collapses to a slim vertical status bar when no run is active. |
| **`node:sc_1` / `node:r_1` Artifacts** | The scanner/search run node artifacts the flow reads back on completion: `scannerRowsFromArtifacts` pulls `output_rows.bucket`, `reportRowsFromArtifacts` pulls `output_rows.rated` then falls back to `merge_table`. |
| **Scan Run** | Phase 2 run: `Universe → Scanner` graph (`scanRunBody`), pasted universe → `force_symbols`. Drives the results table. |
| **Search Run** | Phase 4 run: `Universe → Scanner → Search → Report` graph (`searchRunBody`) with surviving symbols as the paste universe — deterministic re-run, no `seed_rows` optimization (fog). The `search` node can fire the runtime `confirm_needed` gate for large batches. |

---

## 照妖鏡 (Zhao) + Premarket families

| Term | Meaning |
|------|---------|
| **照妖鏡 (zhao)** | "Mirror that reveals the demon" — scanner family with two variants (`zhao_variant`): `realtime` (stock vs benchmark today% margin) and `daily` (20d relative strength + 52w-high proximity). No AI Search (rate limits). Backend: `scanners/zhao/`, `models/zhao.py`. |
| **Zhao Realtime** | Manual-trigger anytime. Keep rule: `close > SMA20` AND stock today% − benchmark today% ≥ `zhao_min_margin_pct` (default 1.0). Benchmark = `zhao_benchmark` (SPY\|QQQ, default SPY). Tier 5≥3.0 / 4≥1.5 / 3>0 / 2. Ranked by margin desc. |
| **Zhao Daily (EOD)** | Keep rule: `close > SMA20`, 20d RS vs benchmark ≥ `zhao_min_rs_pct`, close within `zhao_max_high_dist_pct` (default 15%) of the 252d high. Ranked by RS desc. Tier = RS + 52w proximity composite. Persists survivors to `scan_signals` for the streak. |
| **Market Margin** | `margin_pct` = stock today% − benchmark today% (both vs prior close). Realtime gate + rank key. |
| **Weak-Day Relative Strength** | `rs_20d` = (stock 20d return %) − (benchmark 20d return %) using close[-1] vs close[-21]. Daily gate + rank key. |
| **52-Week High Proximity** | `pct_from_high` = (close / 252d high − 1) × 100, negative below the high. Daily gate (`≥ −max_high_dist_pct`). |
| **Consecutive-Day Streak** | zhao daily survivor count of consecutive trading dates ending today (`streak = prior + 1`); displayed as 1 / 2 / 3+ (`streak_class`). Same-day re-runs never inflate. |
| **scan_signals** | DB table (`schema.sql`): one row per `(symbol, scan_family, scan_variant, signal_date)` a symbol survived a scan. `Repo.record_scan_signals` (idempotent upsert) + `Repo.get_scan_streaks` (strictly prior dates). Wired in `server/app/jobs.py` via `node_overrides["__streaks__"]` (zhao daily only). |
| **SIC Sector** | Polygon Ticker Details `sic_description` — the sector string attached to scanner rows (zhao `sector`, premarket `sector`) for sector grouping. No other sector source. |
| **Premarket grep** | `premarket` family, single Polygon snapshot call at run time (~9:00–9:15 ET). Filter `change_pct ≥ premarket_min_change_pct` (default 5.0), sort desc, cap to `premarket_cap` (default 300), plus pasted symbols. No AI Search. |
| **Pre-market Change %** | `change_pct` from the Polygon snapshot (`todaysChangePerc`) vs prior close; includes premarket activity from 4am ET (research 03). Must-notice gate + rank key. |
| **Premarket Volume Flag** | Informational `vol_flag`: `volume ≥ premarket_min_vol_mult × 20d ADV` when `premarket_min_vol_mult > 0` (0 = off, flag always False). |
| **Family Has Search** | `FAMILY_HAS_SEARCH` (`web/lib/flow.ts`): `false` for zhao/premarket → stepper is 1→2→3→5 (`phasesForFamily`), and the scanner bucket rows become the report rows directly. |
