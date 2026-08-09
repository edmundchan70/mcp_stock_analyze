# VCP Pipeline — Stock Analyze Project

- **Purpose**: Multi-agent stock scanner that discovers US equities with Volatility Contraction Pattern (VCP) characteristics per Mark Minervini's SEPA methodology. Pure-math pattern detection on OHLCV bars, dual-query Tavily context enrichment for sector/leadership analysis, down-only caps merge structural and contextual signals.
- **Key entry points**: `stock_analyze/cli.py` → `vcp`/`vcp-scan`/`vcp-enrich` subcommands, `stock_analyze/interactive.py` → `run_interactive()` (wizard: pipeline type → VCP Auto/Manual), `stock_analyze/pipeline.py` → `run_daily()` (dispatches on `pipeline_type=daily_vcp_scan`)
- **Depends on**: `tradingview_screener`, `tvDatafeed`, `tavily`, `openai` (OpenRouter), `pydantic`, `pandas`, `numpy`, `rich`, `questionary`
- **Version**: 0.2.0 (implemented)

---

## Project Structure (VCP additions)

```
stock_analyze/
├── scanners/
│   ├── ep/                    # EP pipeline (unchanged)
│   └── vcp/                   # NEW: VCP Agent 1
│       ├── __init__.py        # Lazy-imports run_vcp_scan
│       ├── gates.py           # Stage 2 gate + VCP structural gate + cap rules
│       ├── metrics.py         # VCP pattern detection: RS line, contractions, tight closes, volume decay, 9-param scoring
│       └── runner.py          # run_vcp_scan(), merge_vcp_force_rows()
├── agents/
│   ├── catalyst.py            # EP Agent 2 (unchanged)
│   ├── rating.py              # EP Agent 3 (unchanged)
│   └── enrichment.py          # NEW: VCP Agent 2 — Tavily dual-query + LLM context parsing
├── models/
│   ├── ep.py / catalyst.py / rating.py  # EP schemas (unchanged)
│   └── vcp.py                 # NEW: VcpContraction, VcpStructuralRating, VcpContextEnrichment, VcpRatedStock, buckets
├── data/
│   ├── screener.py            # extended: fetch_us_vcp_universe()
│   └── tradingview.py         # extended: batch_get_stock_data()
├── pipeline.py                # extended: RunConfig.pipeline_type, dispatch in run_daily()
├── interactive.py             # extended: pipeline type selection, VCP wizard paths
└── cli.py                     # extended: vcp, vcp-scan, vcp-enrich subcommands
```

---

## Architecture: 3-Agent VCP Pipeline

```
[TradingView Stage 2 Screener]     [Force Include (user paste)]
        |                                    |
        |  close≥10, SMA alignment,         |  LLM parse → SymbolKeys
        |  ADV≥$10M, mktcap≥$100M           |  Screener lookup + OHLCV fallback
        |                                    |
        +------ merge_vcp_force_rows() ------+
                        |
                        v
              batch_get_stock_data()  [250 stocks, 300 bars each, persistent WS]
                        |
                        v
                   SPY OHLCV fetch  [1 call, 300 bars]
                        |
                        v
              compute RS line + Stage 2 gate  [RS<70 discard, non-Stage-2 discard]
                        |
                        v
              VCP pattern detection (pure math)
              ┌─ 9 parameters scored ─┐
              │  • Stage 2 trend      │
              │  • 52W-high proximity │
              │  • Contraction count  │
              │  • Trough symmetry    │
              │  • Peak symmetry      │
              │  • Dollar range       │
              │  • Depth percentage   │
              │  • Tight closes       │
              │  • Volume decay       │
              │  • Time contraction   │
              └───────────────────────┘
                        |
          ┌-------------+-------------┐
          v                           v
    ┌──────────┐               ┌──────────┐
    │ 5★ Bucket│               │ 4★ Bucket│       3★ = discarded
    └──────────┘               └──────────┘
          |                           |
          +--- 4–5★ pass to Agent 2 --+
                        |
                        v
              Tavily dual-query per stock
              ┌──────────────────────────────┐
              │ Query 1: Taxonomy Vector     │  topic=finance, depth=basic, max_results=5
              │ "{symbol} {name} stock       │
              │  sector industry             │
              │  classification competitors" │
              ├──────────────────────────────┤
              │ Query 2: Leadership Vector   │  topic=news, depth=advanced, time_range=month
              │ "{symbol} {name} market      │
              │  leader competitors share    │
              │  growth drivers catalysts"   │
              └──────────────────────────────┘
                        |
                        v
              LLM parse → VcpContextEnrichment JSON
              (sector_taxonomy, market_leadership, thematic_momentum)
                        |
                        v
              Apply down-only caps
              5★→4★ if non-leader or declining sector
              4★→3★ if declining sector
              3★ stays 3★
                        |
                        v
              Final ranked output (Agent 3 artifact)
              sort by (-final_rating, -structural_rating, symbol)
```

---

## Agent 1 — VCP Structural Scanner (`scanners/vcp/`)

1. `fetch_us_vcp_universe()` (`data/screener.py`, new) queries TradingView screener with Stage 2 pre-filters: close≥10, close>SMA50, close>SMA200, ADV≥$10M, mktcap≥$100M, type=stock, america market.
2. Force-include: reuses `parse_force_include_text()` (`force_include.py`), screener lookup via `fetch_symbols()` (VCP columns), OHLCV fallback via `enrich_from_ohlcv()` for missed symbols.
3. `merge_vcp_force_rows()` (`scanners/vcp/runner.py`) merges screener + force rows; screener row wins on duplicate.
4. `batch_get_stock_data()` (`tradingview_data.py`, new) fetches 300 daily bars for all merged stocks: persistent WebSocket, refresh every 50 fetches, 300ms inter-fetch delay, soft-fails individual symbols. Accepts optional `on_progress: Callable[[int, int, str, str], None]` callback fired after each successful fetch — throttling is the caller's responsibility.
5. **Batch progress ticker**: `run_vcp_scan()` accepts `batch_progress: Optional[RunProgress]`. When set, starts a Rich progress bar (`begin_ticker(len(symbols), "Batch OHLCV", throttle=5)`) before the batch fetch and closes it after. The `ticker()` method throttle-every-5 prevents terminal flicker at ~3 fetches/sec. `execute_vcp_scan()` passes `reporter` through via `batch_progress` param.
6. SPY OHLCV fetch for RS line computation.
7. `compute_rs_line(df, spy_df)` → RS series per bar.
8. `check_stage2_trend(df)` → boolean (price > SMA50 > SMA150 > SMA200, rising SMA200, near 52W-high).
9. `passes_stage2_gate(stock)` (`scanners/vcp/gates.py`) — discard RS<70, non-Stage-2.
10. `find_vcp_swing_points(df)` → swing highs/lows.
11. `detect_contractions(df, swings)` → list of `VcpContraction` objects.
12. `score_vcp(df, spy_df)` (`scanners/vcp/metrics.py`) → `VcpStructuralRating` (1–5★, computed from 9 parameters).
13. `passes_vcp_gate(rating)` (`scanners/vcp/gates.py`) — 3★ discarded, 4–5★ pass.
14. `run_vcp_scan()` (`scanners/vcp/runner.py`) returns `VcpScanBucket` with 5★ and 4★ buckets.

## Agent 2 — VCP Context Enrichment (`agents/enrichment.py`)

1. `enrich_with_vcp_context(stocks, company_names)` per 4–5★ stock:
   - Two parallel Tavily asynchronous calls (asyncio semaphore bounded per Tavily rate limit)
   - Query 1 (taxonomy): `topic=finance`, `search_depth=basic`, `max_results=5`, `chunks_per_source=2`
   - Query 2 (leadership): `topic=news`, `search_depth=advanced`, `time_range=month`, `max_results=5`, `chunks_per_source=3`
   - URL deduplication between queries
   - LLM (OpenRouter, DeepSeek V4 Flash) parses merged results into `VcpContextEnrichment` JSON schema
2. Applies down-only caps: `apply_vcp_caps(structural_rating, context)` → final_rating.
3. Uses model `deepseek/deepseek-v4-flash-0731` (configurable via `VCP_ENRICHMENT_LLM_MODEL` env).

## Agent 3 — Final Report (`pipeline.py`)

1. Merges structural rating + context enrichment per stock.
2. Applies cap rules.
3. Sorts by `(-final_rating, -structural_rating, symbol)`.
4. Writes `{name}_agent3.json` as `VcpRatedBucket`.

---

## VCP Context Enrichment JSON Schema

```
VcpContextEnrichment:
  symbol: str
  company_name: str
  sector_taxonomy:
    broad_sector: str
    specific_industry_group: str
    direct_competitors: list[str] (max 3)
  market_leadership:
    is_category_leader: bool
    leadership_rank_estimate: int (1-10, optional)
    competitive_advantage_summary: str (max 250 chars)
  thematic_momentum:
    primary_growth_drivers: list[str]
    industry_group_strength_flag: "HOT_SECTOR" | "NEUTRAL" | "DECLINING_GROUP"
    macro_catalyst_narrative: str (max 300 chars, optional)
```

---

## Key Symbols (Planned)

### `stock_analyze/models/vcp.py`

| Symbol | Line | Role |
|--------|------|------|
| `VcpContraction` | `:12` | Single contraction wave: index, high_pivot, low_pivot, dollar_range, depth_pct, avg_volume, duration_days |
| `VcpStructuralRating` | `:20` | 9-parameter scores + structural_rating (1-5) + structural_label + contractions list |
| `STRUCTURAL_LABELS` | `:49` | dict[int, str]: 1-2→disqualified, 3→sub_standard, 4→strong, 5→textbook |
| `IndustryGroupStrengthFlag` | `:57` | Literal["HOT_SECTOR", "NEUTRAL", "DECLINING_GROUP"] |
| `VcpContextEnrichment` | `:60` | Tavily+LLM output: sector, industry, strength_flag, is_category_leader, top_competitors, market_leadership_context, growth_catalysts, thematic_momentum |
| `VcpRatedStock` | `:86` | Merge: structural + context + final_rating (post-cap) + cap_applied/cap_reason |
| `VcpScanBucket` | `:119` | Envelope: five_star, four_star, three_star lists + counts + universe_source |
| `VcpEnrichedBucket` | `:127` | Agent 2 output: count + list[VcpContextEnrichment] |
| `VcpRatedBucket` | `:132` | Agent 3 output: count + list[VcpRatedStock] (sorted best→worst) |

### `stock_analyze/scanners/vcp/metrics.py`

| Symbol | Line | Role |
|--------|------|------|
| `compute_rs_line(df, spy_df)` | `:30` | Return stock_close / spy_close as aligned daily Series |
| `compute_rs_rating(rs_line)` | `:40` | Return RS value at latest bar as percentile rank (0-100) |
| `check_stage2_trend(df, rs_rating)` | `:53` | Check SMA alignment, rising 200, RS. Returns (is_stage2, meta dict) |
| `find_vcp_swing_points(df, window=10)` | `:90` | Find pivot highs/lows using rolling max/min with window |
| `detect_contractions(df, swings)` | `:133` | Build list[VcpContraction] from alternating high→low pairs |
| `check_tight_closes(df, n_days=4)` | `:162` | Returns (found, span_pct, cv_pct) for last N days |
| `score_stage2_and_proximity(meta)` | `:177` | Score Stage 2 + 52W-high proximity → 5/4/3 |
| `score_contraction_count(contractions)` | `:192` | k=3-4→5★, k=2/5→4★, other→3★ |
| `score_trough_symmetry(contractions)` | `:199` | Lows must be strictly higher for 5★ |
| `score_peak_symmetry(contractions)` | `:218` | Highs flat/rising for 5★, descending triangle→3★ |
| `score_dollar_range(contractions)` | `:235` | Ranges must shrink ≤0.75·prev for 5★ |
| `score_depth(contractions)` | `:252` | Depths must monotonically fall for 5★ |
| `score_tight_closes(span_pct, cv_pct, found)` | `:269` | span≤1.25%+CV≤0.8%→5★ |
| `score_volume_decay(contractions, df)` | `:280` | ≥15% drop/wave for 5★, pivot vol ≤40% SMA20 |
| `score_time_contraction(contractions)` | `:298` | T1>T2>T3 for 5★, Tk≫T1→3★ |
| `score_vcp(df, spy_df, ...)` | `:323` | Orchestrator: all 9 params → VcpStructuralRating (1-5★) |

### `stock_analyze/scanners/vcp/gates.py`

| Symbol | Line | Role |
|--------|------|------|
| `MIN_ADV_DOLLAR` | `:7` | Shared constant: $10M ADV$ threshold used by both screener pre-filter and post-OHLCV liquidity gate |
| `compute_adv_dollar(df, window=60)` | `:17` | Return avg daily dollar volume from OHLCV tail(60) of volume × close |
| `passes_liquidity_gate(df, min_adv, window=60)` | `:29` | True if 60d ADV$ ≥ $10M. Hard pre-requisite always enforced post-OHLCV-fetch — not gated on `apply_gates`. Rejects untradeable stocks even in "Run all pasted" mode |
| `passes_stage2_gate(rating)` | `:43` | True if RS ≥ 70 and Stage 2 trend valid |
| `passes_vcp_gate(rating)` | `:48` | True if structural_rating ≥ 4 |
| `apply_vcp_caps(structural, context)` | `:56` | Apply down-only cap rules, returns (final_rating, cap_applied, cap_reason) |
| `build_rated_stock(structural, context)` | `:97` | Merge structural + context → VcpRatedStock |

### `stock_analyze/scanners/vcp/runner.py`

| Symbol | Line | Role |
|--------|------|------|
| `merge_vcp_force_rows(...)` | `:25` | Merge screener + force rows, screener wins on duplicate, returns (rows, force_set, source) |
| `_fetch_spy()` | `:56` | Fetch SPY daily OHLCV for RS line, tries AMEX then NYSE |
| `run_vcp_scan(...)` | `:72` | Full Agent 1 pipeline: merge→batch OHLCV→SPY→gate→detect→classify→VcpScanBucket. Accepts `batch_progress: Optional[RunProgress]` for live Rich progress bar during batch fetch |

### `stock_analyze/agents/enrichment.py`

| Symbol | Line | Role |
|--------|------|------|
| `SYSTEM_PROMPT` | `:36` | LLM prompt for VCP context parsing |
| `_make_tavily_search(api_key)` | `:57` | Factory returning (taxonomy_search_fn, leadership_search_fn) |
| `_make_openrouter_parser(api_key, model)` | `:91` | Factory for LLM context parsing → dict |
| `_dedup_urls(a, b)` | `:137` | Merge snippet lists, deduplicate by URL |
| `enrich_with_vcp_context(...)` | `:164` | Per stock: parallel Tavily dual-query → dedup → LLM parse → VcpContextEnrichment. Async with semaphore |
| `load_vcp_stocks_from_input(payload)` | `:247` | Extract VCP stock dicts from Agent 1 JSON (bare list, stocks key, or VcpScanBucket style) |

### `stock_analyze/data/screener.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `VCP_COLUMNS` | `:27` | TradingView field list for VCP screener pre-filter |
| `fetch_us_vcp_universe()` | `:65` | Stage 2 pre-filter query (close≥10, SMA alignment, ADV≥$10M, mktcap≥$100M), returns list[dict] |

### `tradingview_data.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `batch_get_stock_data(...)` | `:448` | Persistent WS batch fetch, refresh every N, 300ms inter-delay, soft-fail per symbol. Accepts `on_progress` callback `(idx, total, symbol, exchange)` fired after each successful fetch |

### `stock_analyze/pipeline.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `RunConfig.pipeline_type` | `:61` | Dispatch field: "daily_ep_scan" or "daily_vcp_scan" |
| `execute_vcp_scan()` | `:238` | VCP Agent 1: screener → force merge → batch OHLCV → SPY → run_vcp_scan → JSON. Accepts `batch_progress: Optional[RunProgress]` |
| `execute_vcp_enrichment()` | `:293` | VCP Agents 2-3: enrich → cap → VcpRatedBucket |
| `format_vcp_rating_table()` | `:346` | Plain-text table of VCP rated stocks |
| `_run_daily_vcp()` | `:353` | Full VCP pipeline: Agent 1 → Agent 2-3 → write artifacts |
| `run_daily()` | `:447` | Dispatches on pipeline_type to EP or VCP path |

---

## Test Structure

| Test File | Tests | Type |
|-----------|-------|------|
| `test_vcp_models.py` | 9 | Pydantic validation, edge cases |
| `test_vcp_metrics.py` | ~35 | RS line, Stage 2, swing points, contractions, tight closes, golden scores |
| `test_vcp_gates.py` | 14 | Stage 2 gate, VCP gate, all cap rules |
| `test_vcp_runner.py` | 6 | merge rows, run_vcp_scan (mocked OHLCV) |
| `test_vcp_enrichment.py` | 7 | query building, parsing, cap logic, soft-fail (mocked) |
| `test_pipeline_vcp.py` | 5 | RunConfig dispatch, execute_vcp_scan/enrichment |
| `test_cli_vcp.py` | 11 | argparse subcommands, help text |

Run: `python -m pytest tests/test_vcp_*.py tests/test_cli_vcp.py tests/test_pipeline_vcp.py -q`

---

## External API / Service Dependencies

| Service | Library | Used By | Env Var | Credits / Cost |
|---------|---------|---------|---------|----------------|
| TradingView Screener | `tradingview-screener>=3.0.0` | `data/screener.py` (Agent 1 universe) | `TV_USERNAME`, `TV_PASSWORD` (optional) | Free |
| TradingView OHLCV | `tvDatafeed` | `tradingview_data.py` (batch fetch: batch_get_stock_data(), SPY) | Same as above | Free |
| Tavily News Search | `tavily-python>=0.5.0` | `agents/enrichment.py` (dual-query per stock) | `TAVILY_API_KEY` | 1,000 free/month (2-4 credits/stock) |
| OpenRouter LLM | `openai>=2.16` (pointed at openrouter.ai) | `agents/enrichment.py` (context parsing) | `OPENROUTER_API_KEY` | ~$0.003-0.005/call (DeepSeek V4 Flash) |

---

## Configuration (Environment Variables)

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `TAVILY_API_KEY` | (required) | enrichment.py | Tavily dual-query |
| `OPENROUTER_API_KEY` | (required) | enrichment.py | LLM context parsing |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | enrichment.py | OpenRouter endpoint |
| `VCP_ENRICHMENT_LLM_MODEL` | `deepseek/deepseek-v4-flash-0731` | enrichment.py | Model for Agent 2 context parsing |

---

## User Routes, Cost, and Timing

### Route A — Auto (Screener)

1. Wizard: VCP → Auto Run → optional force-include paste → name → run
2. Screener fetches 200-300 Stage 2 candidates
3. Batch OHLCV for all + SPY
4. Stage 2 gate (discards ~30-40%)
5. VCP structural on ~120-180 survivors
6. 4-5★ = Tavily + LLM (~15-30 stocks)
7. Final ranked output

| API Calls | Tavily Credits | LLM Cost | Time | Monthly (20 runs) |
|-----------|---------------|----------|------|-------------------|
| 1 screener + 1 SPY + 250 batch + 30-60 Tavily + 15-30 LLM | ~120 | ~$0.10 | ~8-10 min | 600 credits, ~$2 LLM |

### Route B — Manual: Apply Gate

1. Wizard: VCP → Manual Run → paste → "Apply Gate" → name → run
2. LLM parse paste → screener lookup + OHLCV fallback → batch OHLCV → SPY
3. Stage 2 gate → VCP detect → Tavily on 4-5★ only
4. Final output

| API Calls (50 pasted) | Tavily Credits | LLM Cost | Time |
|-----------------------|---------------|----------|------|
| 1 LLM parse + 1 screener + 1 SPY + 50 batch + 10-20 Tavily + 5-10 LLM | ~40 | ~$0.05 | ~2-3 min |

### Route C — Manual: Run All Pasted

1. Wizard: VCP → Manual Run → paste → "Run all pasted" → name → run
2. Same as Route B but Stage 2 + VCP gates are SKIPPED
3. All pasted stocks get OHLCV + VCP detection + Tavily enrichment

| API Calls (50 pasted) | Tavily Credits | LLM Cost | Time |
|-----------------------|---------------|----------|------|
| 1 LLM parse + 1 screener + 1 SPY + 50 batch + 20-40 Tavily + 10-20 LLM | ~80 | ~$0.08 | ~2-3 min |

### Route D — CLI: `vcp-scan`

```bash
python -m stock_analyze vcp-scan
```

Agent 1 only: screener → OHLCV → structural rating. No Tavily, no LLM.

| API Calls | Tavily | LLM | Time |
|-----------|--------|-----|------|
| 1 screener + 1 SPY + 250 batch OHLCV | 0 | $0 | ~7 min |

### Route E — CLI: `vcp-enrich`

```bash
python -m stock_analyze vcp-enrich --input output/.../agent1.json
```

Re-run Tavily enrichment on existing Agent 1 artifact.

| API Calls (20 stocks) | Tavily Credits | LLM Cost | Time |
|----------------------|---------------|----------|------|
| 40 Tavily + 20 LLM | ~80 | ~$0.08 | ~1-2 min |

---

## Edge Cases / Gotchas

- **Liquidity gate is always enforced**: `passes_liquidity_gate()` fires before VCP scoring regardless of `apply_gates`. Even in "Run all pasted" mode, illiquid stocks (ADV$ < $10M) are silently discarded. This closes the gap where force-included symbols bypass the screener's ADV pre-filter.
- **Four-gate pipeline order**: Liquidity (Gate 1) → VCP scoring → Stage 2 (Gate 2) → VCP Structural (Gate 3). Liquidity is always-on; Stage 2 and Structural are gated on `apply_gates`. Gate 0 (screener pre-filter) only applies in Auto mode.
- **Force-include bypasses the big screener query**: When a user pastes symbols, `fetch_symbols()` makes a tiny `isin()` query (REST, one call) instead of `fetch_us_vcp_universe()`'s broad universal scan. If the screener misses a symbol, `enrich_with_retry()` falls back to OHLCV with a 5-exchange chain (primary → NASDAQ → NYSE → AMEX → BATS → CBOE, 1 attempt each, fresh WebSocket per attempt).
- **Failed force-include symbols reported but not re-run**: After all exchange fallbacks are exhausted, the symbol is recorded in `_failed_force`, printed in red on the terminal with a hint to fix the ticker and re-run manually. There is no interactive re-run prompt.
- **WebSocket lifecycle**: `_close_tv_socket()` is called before/after every single-fetch `get_hist()`, every 50 batch fetches, and on any batch error. Prevents stale WebSocket timeouts from cascading.
- **Batch OHLCV socket refresh**: `batch_get_stock_data()` refreshes the WebSocket every 50 stocks and on any WebSocket error. If a single stock's fetch fails, the socket is reconnected before the next stock. Failed stocks get a `None` DataFrame and are logged as soft-fails.
- **SPY fetch failure**: If SPY OHLCV fetch fails, RS line cannot be computed. All stocks get RS = None; Stage 2 gate falls back to checking SMA alignment + 52W-high proximity only.
- **Tavily rate limiting**: Bounded asyncio semaphore (5 concurrent per 120 RPM tier). If Tavily returns errors, the stock is soft-failed with an error enrichment entry rather than aborting the batch.
- **Company name missing**: If the screener `description` field is empty, a batch LLM call resolves all missing names (one prompt for all unresolved symbols). If LLM fails, Tavily query uses symbol-only (lower precision but functional).
- **No 4–5★ survivors**: If the VCP gate produces zero 4–5★ stocks, Agent 2 (Tavily) is skipped entirely. The run artifact still writes `agent1.json` with all structural ratings. Agent 2 and 3 artifacts contain empty buckets.
- **Duplicate merge priority**: In `merge_vcp_force_rows()`, screener rows win over force rows when the same symbolKey appears in both.
- **Down-only caps never boost**: `apply_vcp_caps` only clamps the structural rating down based on context. Even a HOT_SECTOR + leading company can't make a 3★ structural VCP become 4★.
- **Context enrichment is VCP-specific**: EP's `enrich_with_catalysts()` searches for earnings/news events. VCP's `enrich_with_vcp_context()` searches for sector/industry/leadership signals. They use different queries, different LLM prompts, and different output schemas.
- **MIN_ADV_DOLLAR shared threshold**: Both the screener pre-filter (`screener.py:119`) and the post-OHLCV liquidity gate (`gates.py:7`) import the same `MIN_ADV_DOLLAR = 10_000_000` constant from `gates.py`. Changing it in one place affects both.
