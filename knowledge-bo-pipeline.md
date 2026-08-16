# BO Pipeline — Qullamaggie Breakout Setup Detector

- **Purpose**: Pure-math detector for Kristjan Kullamägi "Qullamaggie Breakout" setups: stocks with extreme prior momentum (impulse ≥ 30% over 20–63d), a tightening 5–40d base (VCI ≤ 0.65), a KDE resistance pivot in the base's upper quartile, higher lows, and a breakout close above pivot with volume surge ≥ 1.5× baseline while price "surfs" the EMA10. Formatted exactly like the VCP pipeline (3 agents, wizard/CLI/pipeline integration identical).
- **Key entry points**: `stock_analyze/cli.py` → `bo`/`bo-scan`/`bo-enrich` subcommands (`cli.py:100,106,112`), `stock_analyze/interactive.py` → "Daily BO scan" pipeline choice, `stock_analyze/pipeline.py` → `run_daily()` dispatches on `pipeline_type="daily_bo_scan"` → `_run_daily_bo()` (`pipeline.py:850`)
- **Depends on**: `polygon-api-client` (Polygon.io OHLCV + Ticker Details + Snapshot), `pydantic`, `pandas`, `numpy`. Agent 2–3 reuses VCP's `agents/enrichment.py` (Tavily + OpenRouter) and VCP's `apply_vcp_caps`. Pre-market data via `stock_analyze/data/polygon.py` (`fetch_premarket_aggs`, `get_premarket_data`). Market-wide universe via `fetch_market_snapshot`/`prefilter_snapshot`/`resolve_market_caps` (`data/polygon.py`).
- **Depended by**: wizard `_run_auto`/`_run_manual` (`interactive.py`), CLI handlers (`cli.py:268,301,324`), daily run dispatch (`pipeline.py:850`), dashboard trigger (`server/app/jobs.py` → `build_run_config`)
- **Version**: 0.5.0 (market-wide snapshot sweep universe, `MIN_MARKET_CAP` bumped to $300M, `use_screener` sweep path in `execute_bo_scan`, dashboard "Full market sweep" trigger)

---

## Project Structure (BO additions)

```
stock_analyze/
├── scanners/
│   ├── vcp/                    # VCP Agent 1 (unchanged; shared gates + RS metrics reused)
│   └── bo/                     # BO Agent 1
│       ├── __init__.py         # Lazy-imports run_bo_scan
│       ├── gates.py            # ADR20 envelope + BO gate + build_bo_rated_stock (reuses VCP caps)
│       ├── metrics.py          # Prior impulse, ADR20, VCI, MA stack/surfing, KDE pivot, higher lows,
│       │                       # volume signature, base detection, breakout trigger, variants, scoring
│       ├── runner.py           # run_bo_scan(), merge_bo_force_rows(), _fetch_spy()
│       └── watchlist.py        # NEW: funnel gatekeeper — WATCHLIST_PROFILES, G2/G3/G4/G5 gates,
│                               # compute_q_base, q_base_to_stars, apply_funnel(), tradable_count
├── models/
│   └── bo.py                   # BoBase, BoSetupRating (extended: adv_20d, ema10_dist_pct,
│                               # ema10_rising, dryup_vol_ratio, tightness, q_base, funnel_stars),
│                               # BoScanBucket, BoEnrichedBucket, BoRatedStock, BoRatedBucket
├── data/
│   └── screener.py             # extended: fetch_us_bo_universe() (same Stage-2 pre-filter, reuses VCP_COLUMNS)
├── pipeline.py                 # extended: execute_bo_scan/enrichment, format_bo_rating_table,
│                               # _run_daily_bo (funnel gate replaces rating>=4), funnel survivors → enrichment
├── interactive.py              # extended: "Qullamaggie BO (Classic)" pipeline choice,
│                               # _run_bo_interactive() with gap-options free loop prompt
└── cli.py                      # extended: bo / bo-scan / bo-enrich subcommands, --profile flag
```

---

## Architecture: 3-Agent BO Pipeline (VCP-mirrored)

```
[Market Snapshot Sweep (use_screener=True)]     [Force Include (user paste)]
        |                                              |
        |  /v2/snapshot → prefilter (price≥$10,         |  LLM parse → SymbolKeys
        |  $vol proxy ≥$10M) → resolve_market_caps      |  resolve_force_symbol
        |  (mcap ≥ $300M)                               |
        +----------- merge_bo_force_rows() -------------+
                        |
                        v
         batch_get_stock_data()  [300 bars, persistent WS, on_progress ticker]
                        |
                        v
                   SPY OHLCV fetch  [AMEX → NYSE fallback]
                        |
                        v
              Liquidity gate (ALWAYS on, even "Run all pasted")
              ADV$ ≥ $10M → discard below
                        |
                        v
              score_bo_setup() (pure math, 4 research stages)
              ┌──────────────────────────────┐
              │ S1 ADR20 ∈ [4%,12%] envelope │
              │ S2 prior impulse ≥30% + MA   │
              │    stack + EMA50 slope >0    │
              │ S3 base 5–40d, VCI≤0.65,    │
              │    KDE pivot, higher lows≥1  │
              │ S4 close>pivot + surge≥1.5×  │
              └──────────────────────────────┘
                        |
          variant? classic / lower_base / none
                        |
          ┌-------------+-------------┐
          v                           v
    [classic] surge≥3× → 5★     [lower_base] capped 4★
    [classic] surge≥2× → 4★     [classic] 4★ + RS≥85 → 5★
    else 3★ ; close>8% above EMA10 → clamp 3★ (extension)
                        |
                        v
              BoScanBucket (5★/4★/3★)  [3★ discarded by passes_bo_gate (legacy)]
                        |
                        v
         ┌─── Funnel Gate (NEW: replaces rating≥4) ──┐
         │  G1: prior_impulse                         │
         │  G2: 20d ADV$ ≥ floor (profile-dependent)  │
         │  G3: |close-EMA10| ≤ max + EMA10 rising    │
         │  G4: base 5–N days (profile-dependent)      │
         │  G5: dry-up vol ratio (scoring-only)        │
         │  Q_base ≥ 60 (3★ floor)                     │
         └───────────────────┬─────────────────────────┘
                             │
             ┌───────────────┴───────────────┐
             │  tradable ≥ 5?  YES → proceed │
             │  NO → gap-options prompt      │
             │  best / moderate-lose / widen │
             │  (free loop, pick repeatedly)  │
             └───────────────┬───────────────┘
                             v
        Agent 2 (REUSED VCP): enrich_with_vcp_context → VcpContextEnrichment
        Agent 3: build_bo_rated_stock → apply_vcp_caps (on funnel_stars)
        sort (-final_rating, symbol) → BoRatedBucket → {name}_agent3.json
```

---

## Agent 1 — BO Structural Scanner (`scanners/bo/`)

1. **Paste path**: `resolve_force_symbol()` (`data/polygon.py:235`) resolves pasted symbols via Polygon Ticker Details.
2. **Sweep path** (`use_screener=True`): `_execute_bo_sweep()` (`pipeline.py`) → `fetch_market_snapshot()` → `prefilter_snapshot()` → `resolve_market_caps()` (mcap ≥ $300M) → `run_bo_scan(universe_source="snapshot")`.
3. `merge_bo_force_rows()` (`scanners/bo/runner.py:27`) — screener/snapshot rows win on duplicate key; returns (rows, force_set, source=force|snapshot|screener|hybrid).
4. `batch_get_stock_data()` with `batch_progress` Rich ticker (throttle=5), same 300ms inter-delay / refresh-every-50 as VCP.
5. `_fetch_spy()` (`runner.py:58`) — SPY 300 bars, AMEX then NYSE.
6. `score_bo_setup(df, benchmark=None, ...)` (`metrics.py:430`) → `Optional[BoSetupRating]`.
7. `passes_liquidity_gate(df)` always enforced per stock before scoring (`runner.py:170`).
8. `passes_bo_gate(rating)` (`gates.py:18`) — rating ≥ 4 pass to enrichment; 3★ discarded. Skipped when `apply_gates=False` (Run-all-pasted).
9. `run_bo_scan(...)` (`runner.py:81`) → `BoScanBucket`.

### Quantitative rules (research-sourced, from `Qullamaggie Breakout Quantitative Test Suite.txt`)

| Metric | Rule | Constants (`metrics.py:30-38`) |
|---|---|---|
| Prior impulse | max % gain over rolling 20–63d window ≥ 30% | `MIN_IMPULSE_PCT=30.0` |
| ADR20 | 20d avg daily range % ∈ [4%, 12%] | `ADR_LO=4.0`, `ADR_HI=12.0` (gates.py) |
| Base duration | 5–40 trading days | `BASE_MIN_DAYS=5`, `BASE_MAX_DAYS=40` |
| VCI | ATR5/ATR20 ≤ 0.65 + narrow 3-day range ≤ 0.6·ADR20 | `VCI_MAX=0.65` |
| MA stack / surfing | EMA10>EMA20, EMA50 slope>0, close within 8% of EMA10 | `SURFING_MAX_PCT=8.0` |
| KDE pivot | Gaussian KDE (bandwidth=3% price) over base peaks, mode in upper quartile | `bandwidth_pct=0.03` |
| Higher lows | consecutive higher swing lows into pivot ≥ 1 | `S_HL >= 1` |
| Volume signature | **dual condition (UT-06)**: base-end dry-up ≤ 0.5× baseline **and** breakout surge ≥ 1.5× baseline — both enforced as the volume essential | `DRYUP_MAX=0.5`, `SURGE_MIN=1.5`, `SURGE_STRONG=2.0`, `SURGE_TEXTBOOK=3.0` |
| Extension cap | close > 8% above EMA10 → clamp to 3★ (EC-01); SMA50 distance reported as `sma50_extension_pct` (never a gate) | — |

### `score_bo_setup` edge semantics

- Returns `None` when `len(df) < MIN_BARS` (90) — need 63d impulse + 40d base + buffer.
- Valid data but no base/breakout → 3★.
- 9 "essential" booleans must ALL be true for >3★: `prior_impulse, adr20, base_duration, vci, ma_stack, pivot_kde, higher_lows, dryup, volume_surge` (volume signature is a dual condition — dry-up then surge). Canonical ordering in `ESSENTIAL_KEYS`.
- `extension=True` (close >8% above EMA10) clamps to 3★ regardless of other params (EC-01).
- `lower_base` variant capped at 4★ (needs ≥1.5× surge). Only `classic` reaches 5★ (≥3× surge, or 4★→5★ when RS≥85).
- RS (`benchmark`) is a boost, never a hard reject.

### Base detection specifics

- `detect_bases(df)` (`metrics.py:336`) — for each end bar `e`, the base start window is anchored at the most recent structural peak (`argmax(highs[:e+1])`), `s` ∈ `[max(peak_idx, e-40+1), e-10+1]`. Keeps the candidate with lowest VCI per end bar, then `_dedup_bases` drops overlapping bases (latest-end wins).
- `_build_base_candidate` (`metrics.py:271`) **excludes the anchor peak bar from the base's high/low envelope** (`start = s+1 if s == peak_idx`) — the peak is the top of the prior move, not base resistance. Also requires VCI ≤ 0.65, narrow 3-day pre-base range, ≥2 local peaks, a KDE pivot in `[base_low, base_high]`, and `higher_lows ≥ 1`.
- VCI for scoring is measured over `df.iloc[:base.end_idx+1]` only (`metrics.py:458`) — breakout bars would inflate ATR5 and hide the contraction.

---

## Agent 2 — BO Context Enrichment (REUSES VCP, no new code)

`execute_bo_enrichment()` (`pipeline.py:484`) calls `enrich_with_vcp_context()` (`agents/enrichment.py`) as-is — same Tavily dual-query (taxonomy + leadership), same LLM parse to `VcpContextEnrichment`, same asyncio semaphore, same soft-fail behavior. Only 4–5★ survivors are enriched (or all pasted in Run-all mode).

## Agent 3 — BO Final Report

`build_bo_rated_stock(setup, context)` (`gates.py:23`) merges `BoSetupRating` + `VcpContextEnrichment` → `BoRatedStock`, reusing `apply_vcp_caps()` (down-only caps identical to VCP: 5★→4★ if non-leader/declining sector, 4★→3★ if declining sector, 3★ stays). Sorted `(-final_rating, symbol)`. Written as `{name}_agent3.json` by `_run_daily_bo()`.

---

## Key Symbols

### `stock_analyze/models/bo.py`

| Symbol | Line | Role |
|--------|------|------|
| `BoBase` | `:11` | Single base: start/end idx, base_high/low, depth_pct, duration_days, KDE pivot, vci, dryup_ratio |
| `BO_VARIANT` | `:25` | Literal["classic", "lower_base", "none"] |
| `BO_LABELS` | `:27` | {3:"sub_standard", 4:"strong", 5:"textbook"} |
| `BoSetupRating` | `:34` | 9 essential boolean params (incl. `dryup`) + measured pct values + extension/sma50_extension_pct + **funnel fields** (adv_20d, ema10_dist_pct, ema10_rising, dryup_vol_ratio, tightness, q_base, funnel_stars) + meta (base/pivot/breakout/rvol10/rs_rating/as_of) + rating Literal[3,4,5] |
| `BoScanBucket` | `:78` | Agent 1 envelope: ratings + five/four/three_star + near_miss + counts + universe_source + gates_applied |
| `BoNearMiss` | `:81` | 3★ near-miss snapshot: symbol, variant, passed/failed_essentials, measured values. Populated when ``apply_gates=True``, ≥7 of 9 essentials passed, not overextended. Sorted closest-first. |
| `BoEnrichedBucket` | `:92` | Agent 2 output: list[VcpContextEnrichment] (reused schema) |
| `BoRatedStock` | `:99` | setup + context merge, final_rating post-cap, cap_applied/cap_reason, error |
| `BoRatedBucket` | `:133` | Agent 3 output sorted best→worst |

### `stock_analyze/scanners/bo/metrics.py`

| Symbol | Line | Role |
|--------|------|------|
| `prior_impulse(closes, window=(20,63))` | `:44` | Max % gain over rolling window (UT-01) |
| `avg_daily_range_pct(df, window=20)` | `:70` | ADR20 % (UT-02) |
| `_atr(df, window)` | `:81` | TR-mean ATR |
| `vci_atr(df, short=5, medium=20)` | `:95` | ATR5/ATR20 contraction ratio (UT-03) |
| `_narrow_three_day(df)` | `:104` | 3-day range ≤ 0.6·ADR20 pre-breakout |
| `ma_stack(df)` | `:117` | EMA10>EMA20, EMA50 slope>0, surfing distance % (UT-04) |
| `find_local_peaks(highs, radius=2)` | `:146` | Local peak highs |
| `kde_pivot(peaks, prices, bandwidth_pct=0.03, range_lo, range_hi)` | `:159` | Gaussian KDE mode in upper quartile (UT-05) |
| `find_local_lows(lows, radius=2)` | `:200` | Local swing lows |
| `higher_lows(df, end_idx, start_idx)` | `:212` | Consecutive strictly higher lows into pivot |
| `_pre_base_volume(df, start_idx, lookback=20)` | `:239` | Pre-base volume baseline |
| `_dryup_ratio(df, start_idx, end_idx)` | `:247` | Base-end volume / baseline |
| `volume_signature(df, base, breakout_idx)` | `:255` | Dry-up + breakout surge (UT-06) |
| `_build_base_candidate(df, s, e, peak_idx)` | `:273` | Validate single base window (excludes anchor peak bar) |
| `_dedup_bases(bases)` | `:323` | Drop overlapping bases, latest-end wins |
| `detect_bases(df)` | `:338` | Enumerate valid bases across series |
| `detect_breakout(df, base, min_surge=1.5)` | `:372` | close>pivot + surge≥min → breakout dict (idx, rvol10, surge, surge_pct) |
| `classify_variant(df, bases)` | `:410` | classic / lower_base / none |
| `score_bo_setup(df, benchmark, *, symbol, exchange, as_of)` | `:432` | Orchestrator → Optional[BoSetupRating] |
| `screen_bucket(ratings)` | `:555` | → BoScanBucket |
| `DRYUP_MAX` | `:35` | 0.5 — base-end volume / baseline ceiling for the dry-up half of the volume essential |
| `ESSENTIAL_KEYS` | `:41` | Canonical list of 9 essential boolean field names for ``derive_near_miss`` |
| `derive_near_miss(ratings, *, threshold)` | `:568` | Derive near-miss watchlist from 3★ ratings passing ≥``threshold`` essentials (default 7) |

### `stock_analyze/scanners/bo/gates.py`

| Symbol | Line | Role |
|--------|------|------|
| `ADR_LO` / `ADR_HI` | `:9-10` | 4.0 / 12.0 ADR envelope |
| `passes_adr_envelope(adr20)` | `:13` | 4% ≤ ADR ≤ 12% |
| `passes_bo_gate(rating)` | `:18` | (legacy) rating ≥ 4 survives — replaced by funnel gate |
| `build_bo_rated_stock(setup, context)` | `:23` | Merge + reuse `apply_vcp_caps` → BoRatedStock. Uses `funnel_stars` when >0 |
| `passes_liquidity_gate` / `MIN_ADV_DOLLAR` | re-exported from `scanners/vcp/gates.py` | Shared $10M ADV$ gate |
| `passes_market_cap_gate` / `MIN_MARKET_CAP` | re-exported from `scanners/vcp/gates.py` | Shared $300M market-cap gate (bumped from $100M) |

### `stock_analyze/scanners/bo/watchlist.py` (NEW — Funnel Gate)

| Symbol | Line | Role |
|--------|------|------|
| `WATCHLIST_PROFILES` | `:19` | 3 profiles: best (ADV $50M / EMA 5% / Base 40d / dryup scoring-only), moderate-lose (ADV $50M / EMA 8% / Base 40d), widen (ADV $30M / EMA 8% / Base 40d) |
| `g2_adv_dollar(adv_20d, floor)` | `:29` | Dollar liquidity gate |
| `g3_ema10_proximity(dist_pct, rising, max_pct)` | `:34` | EMA10 distance + rising check |
| `g4_base_duration(days, base_max)` | `:39` | Base 5 ≤ days ≤ base_max |
| `g5_volume_dryup(ratio, max_ratio)` | `:44` | Dry-up ratio check (None = disabled) |
| `q_base_to_stars(score)` | `:49` | 90→5★, 75→4★, 60→3★, else 0 |
| `compute_q_base(vci, hl, tightness, prior_pct, dryup, surfing)` | `:54` | Composite Q_base score (max 100, 6 parameters) |
| `apply_funnel(ratings, profile)` | `:118` | Run 5-gate funnel → `FunnelResult(survivors, gate)` |
| `tradable_count(survivors)` | `:178` | Count survivors with stars ≥ 3 (Q_base ≥ 60) |
| `FunnelResult` | `:110` | Dataclass: survivors (list[dict]), gate (pass/fail counts) |

### `stock_analyze/scanners/bo/runner.py`

| Symbol | Line | Role |
|--------|------|------|
| `merge_bo_force_rows(...)` | `:27` | Screener/snapshot + force merge; screener/snapshot rows win on duplicate. Accepts `universe_source` ("force"/"snapshot") |
| `_fetch_spy()` | `:58` | SPY 300 bars, AMEX → NYSE fallback |
| `run_bo_scan(...)` | `:81` | Full Agent 1: merge→batch OHLCV→SPY→liquidity→score→**compute funnel fields (adv_20d, ema10_dist_pct, etc.)**. Accepts `batch_progress` + `universe_source` |

### `stock_analyze/pipeline.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `_execute_bo_sweep(...)` | `:374` | Sweep Agent 1: snapshot → prefilter → resolve market caps → `run_bo_scan(universe_source="snapshot")` |
| `execute_bo_scan(...)` | `:414` | BO Agent 1: paste (force) OR sweep (`use_screener=True`) → run_bo_scan → payload + `_counts` |
| `execute_bo_enrichment(...)` | `:484` | BO Agents 2-3: reuse VCP enrichment → BoRatedBucket |
| `format_bo_rating_table(...)` | `:528` | Plain-text table of rated stocks |
| `format_bo_near_miss_table(...)` | `:530` | Plain-text near-miss watchlist for the no-4-5★ short-circuit |
| `_run_daily_bo(...)` | `:671` | Full daily run: Agent1→enrich→rate→artifacts, mirrors `_run_daily_vcp`. Passes `config.use_screener` |
| `run_daily()` dispatch | `:850` | `pipeline_type == "daily_bo_scan"` → `_run_daily_bo`. Relaxed to allow empty `force_keys` when `use_screener` |

### `stock_analyze/data/polygon.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `fetch_market_snapshot()` | `:265` | Polygon `/v2/snapshot/locale/us/markets/stocks/tickers` → list of `{symbol, exchange, price, dollar_volume_proxy, change_pct}` (prev-day bar preferred) |
| `prefilter_snapshot(rows, ...)` | `:307` | Trim snapshot by `min_price=10` + `min_dollar_vol=$10M` before mcap resolution |
| `resolve_market_caps(symbols, ...)` | `:329` | Per-symbol `resolve_force_symbol` + `passes_market_cap_gate` (`min_mcap=$300M`) via ThreadPoolExecutor |

### `stock_analyze/data/screener.py` (removed from use)

| Symbol | Line | Role |
|--------|------|------|
| `fetch_us_bo_universe(...)` | `:138` | Legacy TradingView Stage-2 pre-filter (dead code — screener removed) |

### `stock_analyze/cli.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `bo` subparser | `:100` | Full pipeline command |
| `bo-scan` subparser | `:106` | Agent 1 structural scan only |
| `bo-enrich` subparser | `:112` | Agents 2-3 on existing artifact |
| `run_bo_command` | `:268` | handler |
| `run_bo_scan_command` | `:301` | handler |
| `run_bo_enrich_command` | `:324` | handler |

---

## Test Structure

| Test File | Tests | Type |
|-----------|-------|------|
| `tests/bo_fixtures.py` | — | Deterministic synthetic OHLCV builders (`_make_bo_series(impulse_pct, adr_pct, base_duration, vci, breakout_surge, surfing_dist, ...)`) + scenario helpers |
| `tests/test_bo_models.py` | 14 | Schema validation, variant/label/rubric, funnel field defaults |
| `tests/test_bo_metrics.py` | 30 | UT-01..06 indicators + EC-01..06 edge matrix + golden artifacts + variants |
| `tests/test_bo_gates.py` | 17 | ADR envelope, BO gate, lower_base ceiling, caps |
| `tests/test_bo_runner.py` | 9 | merge rows, run_bo_scan with mocked batch OHLCV |
| `tests/test_bo_watchlist.py` | 41 | NEW: Profile definitions, G2/G3/G4/G5 boundary values (5.0%, 90/75/60), Q_base scoring, apply_funnel gate counts |
| `tests/test_pipeline_bo.py` | ~8 | RunConfig dispatch, execute_bo_scan/enrichment, funnel gate dispatch, wizard wording + **sweep path** (`TestExecuteBoSweep`) |
| `tests/test_cli_bo.py` | ~15 | argparse subcommands, --profile flag, "Qullamaggie BO (Classic)" label |
| `tests/test_polygon_data.py` | +snapshot | `fetch_market_snapshot` (prev-day preference, empty-on-failure), `prefilter_snapshot`, `resolve_market_caps` |
| `tests/test_bo_runner.py` | +2 | `merge_bo_force_rows(universe_source="snapshot")`, `run_bo_scan(universe_source="snapshot")` |
| `server/tests/test_jobs.py` | +1 | `build_run_config` sweep mode (empty `force_keys`) |
| `server/tests/test_routes.py` | +1 | `POST /api/runs` sweep (`use_screener=true`, empty symbols) |
| `web/__tests__/ScanForm.test.tsx` | +1 | universe toggle hides symbols + submits `use_screener=true` |

Run: `python -m pytest tests/test_bo_models.py tests/test_bo_metrics.py tests/test_bo_gates.py tests/test_bo_runner.py tests/test_bo_watchlist.py tests/test_pipeline_bo.py tests/test_cli_bo.py -q`
Full suite: 409 passed, 1 skipped (2026-08-13).

---

## External API / Service Dependencies

| Service | Library | Used By | Env Var | Credits / Cost |
|---------|---------|---------|---------|----------------|
| Polygon OHLCV + Ticker Details | `polygon-api-client` | `data/polygon.py` (batch_get_stock_data, resolve_force_symbol, fetch_spy, fetch_premarket_aggs) | `POLYGON_API_KEY` | Free (5 API calls/min) |
| Polygon Snapshot | `polygon-api-client` (`get_snapshot_all`) | `data/polygon.py` (`fetch_market_snapshot`) | `POLYGON_API_KEY` | Same — 1 call for all ~10k US tickers |
| Polygon Pre-market | `polygon-api-client` | `data/polygon.py` (fetch_premarket_aggs, get_premarket_data) | `POLYGON_API_KEY` | Same — 1 call/symbol for minute bars |
| Tavily News Search | `tavily-python>=0.5.0` | Agent 2 (reused VCP enrichment) | `TAVILY_API_KEY` | 1,000 free/month |
| OpenRouter LLM | `openai>=2.16` (OpenRouter) | Agent 2 LLM parse + force-include paste parse | `OPENROUTER_API_KEY` | ~$0.003-0.005/call |

---

## Configuration (Environment Variables)

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `POLYGON_API_KEY` | (required) | All data (OHLCV, Ticker Details, pre-market) | Polygon.io API key |
| `TAVILY_API_KEY` | (required) | Agent 2 | Context enrichment dual-query |
| `OPENROUTER_API_KEY` | (required) | Agent 2 + paste parse | LLM context parsing |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | enrichment.py | OpenRouter endpoint |
| `VCP_ENRICHMENT_LLM_MODEL` | `deepseek/deepseek-v4-flash-0731` | enrichment.py | Model for Agent 2 (BO reuses VCP env var) |

---

## User Routes

- **Route A — Auto**: Wizard → Pipeline=Qullamaggie BO (Classic) → force paste → name → Agent 1 → funnel gate (best) → gap-options prompt if tradable < 5 → enrich survivors.
- **Route B — Manual Apply Gate**: paste → "Apply Gate" → funnel gate → gap-options prompt → enrich survivors.
- **Route C — Manual Run All**: paste → "Run all pasted" → gates skipped (except liquidity) → all pasted enriched.
- **Route D — CLI `bo`**: --profile best|moderate-lose|widen flag skips prompt; without it, TTY prompts; headless defaults to best.
- **Route E — CLI `bo-scan`**: Agent 1 only, no funnel, no Tavily/LLM.
- **Route F — CLI `bo-enrich --input agent1.json`**: re-run enrichment on existing artifact.
- **Route G — Dashboard "Full market sweep"**: `ScanForm` universe toggle → POST `/api/runs` with `use_screener=true`, `force_symbols=""` → `build_run_config` skips paste parse → `_execute_bo_sweep` discovers the universe from the Polygon snapshot.

Cost/timing: 1 SPY + ~N batch Polygon OHLCV + 0-M Tavily (per survivor) + 0-M/2 LLM (per survivor), ~5-10 min auto route depending on force-include count. The sweep is longer: ~10k snapshot → prefilter → hundreds of Ticker Details calls → hundreds of OHLCV fetches.

---

## Edge Cases / Gotchas

- **Funnel gate replaces structural gate**: `_run_daily_bo()` now applies `apply_funnel(ratings, profile)` instead of `rating >= 4`. Funnel survivors (Q_base ≥ 60) go to enrichment. Structural `BoSetupRating.rating` kept as reference.
- **Funnel fields computed in runner.py**: `adv_20d`, `ema10_dist_pct`, `ema10_rising`, `dryup_vol_ratio`, `tightness` are computed from OHLCV in `run_bo_scan()` right after `score_bo_setup()` and persisted on the rating object.
- **Q_base stars drive final report**: `build_bo_rated_stock()` uses `funnel_stars` (from Q_base scoring) as the base for VCP down-only caps when `funnel_stars > 0`; falls back to structural `rating` otherwise.
- **Gap-options prompt**: triggered only when `tradable_count < 5` in interactive wizard or CLI TTY mode. Free loop — user can pick any profile any number of times, then "Keep what I have" to proceed.
- **--profile flag**: CLI `bo --profile best|moderate-lose|widen` skips the prompt. Default: "best" when headless, or prompt when TTY without --profile.
- **Dry-up is scoring-only**: All three profiles set `dryup: 0` (disabled as a hard gate). Dry-up ratio contributes to Q_base score but never rejects.
- **Polygon-only**: Pipeline uses Polygon.io for all data (symbol resolution, OHLCV, screener removed). Universe is paste (`force`) or market-wide sweep (`snapshot`).
- **Snapshot has no market cap**: `/v2/snapshot` returns `ticker` + `day`/`prevDay` (no `market_cap`). Market cap is only on `/v3/reference/tickers/{ticker}` — so `prefilter_snapshot` (price + dollar-volume proxy) runs first to shrink the list before `resolve_market_caps` issues one Ticker Details call per survivor.
- **Snapshot clears at 3:30am ET**: `/v2/snapshot` resets daily; an intraday sweep uses the partial `day` bar, an after-close sweep uses the full `prev_day` bar (the `fetch_market_snapshot` default).
- **Sweep scale**: snapshot survivors (hundreds) → batch OHLCV is a longer job than paste mode; may need a max-universe cap or rate-limit tuning.
- **`use_screener` is BO-only**: `_execute_bo_sweep` lives in `execute_bo_scan`; VCP/EP still require paste (`force_keys`). `run_daily` relaxes the non-empty `force_keys` guard only when `config.use_screener`.

- **Liquidity gate always enforced**: `passes_liquidity_gate()` fires before BO scoring regardless of `apply_gates` (`runner.py:170`). Illiquid force-included symbols are silently discarded even in Run-all-pasted mode.
- **`apply_gates=False` only bypasses `passes_bo_gate`** — the ADR envelope and liquidity gate are hard requirements. Note `score_bo_setup` still rates 3★ stocks; Run-all passes them to enrichment.
- **Volume signature is a dual condition**: `p_dryup` (base-end volume ≤ 0.5× pre-base baseline) is an essential alongside `p_surge` (`metrics.py:432`). A surge with no prior dry-up stays 3★ (UT-06).
- **SMA50 extension is report-only**: `sma50_extension_pct` (`models/bo.py:63`) is a secondary field, never a rating gate.
- **Anchor peak bar excluded from base envelope** (`metrics.py:279`): base windows start at the impulse high (argmax), but that bar's high is excluded from `base_high`/`base_low` so the pivot KDE isn't skewed by the prior move's top.
- **VCI window ends at `base.end_idx`** (`metrics.py:458`): breakout bars inflate ATR5; scoring VCI over the whole df would falsely pass a non-contracting base.
- **Extension clamp beats everything**: close >8% above EMA10 forces 3★ even when all 8 essentials pass (EC-01).
- **`lower_base` never reaches 5★**: two-base sequence (base B below base A's post-completion high, close above B's high but ≤ A's high×1.01) capped at 4★; `classic` needs ≥2× surge for 4★, ≥3× for 5★.
- **`score_bo_setup` returns `None` for <90 bars** — dropped from bucket entirely (not rated 3★). Runner skips `None` ratings.
- **RS is boost-only**: `rs_rating ≥ 85` bumps classic 4★→5★; low RS never rejects (research does not gate on RS).
- **No 4–5★ survivors**: `_run_daily_bo` (`pipeline.py:721`) short-circuits to a completed run with only `agent1.json`, no enrichment. The near-miss watchlist (3★ ratings passing ≥7/9 essentials) is printed as a table before the short-circuit message.
- **Down-only caps never boost**: reuse of `apply_vcp_caps` means context can only clamp ratings down.
- **Near-miss computed only with gates**: when `apply_gates=False` (Run-all-pasted), `derive_near_miss` is not called (`runner.py`). Also `extension=True` excludes near-miss regardless of essential count.
- **dryup persisted on BoSetupRating**: both `dryup: bool` and `dryup_ratio: float` are now saved fields (defaults `True`/`1.0` for test helpers).
- **Duplicate merge priority**: screener rows beat force rows in `merge_bo_force_rows`.
- **Force-include fallback chain**: symbols missed by the screener go through `enrich_with_retry()` (primary exchange + NASDAQ→NYSE→AMEX→BATS→CBOE); still-missing symbols recorded in `_failed_force` and printed in red — no interactive re-run.
- **Batch OHLCV fallback**: if `batch_get_stock_data` import fails, runner falls back to per-symbol `get_stock_data` single fetches (`runner.py:131-143`).
- **SPY fetch failure** → empty benchmark → all `rs_rating=None`; scoring proceeds (RS optional).
- **Screening core is pure math** — no LLM in Agent 1 (research directive); LLM only in Agent 2 (reused) and force-paste parsing.

### Run Artifacts (all pipelines)

Each daily run writes the following files to `output/<date>/<HHMMSS>_<name>/`:

| File | Writer | Description |
|------|--------|-------------|
| `run_meta.json` | `run_daily()` | Run metadata: name, pipeline_type, start/end time, steps_completed, status |
| `{name}_agent1.json` | `execute_*_scan()` | Agent 1 output (ratings, buckets, counts) |
| `{name}_agent2.json` | execute enrichment | Agent 2 output (context enrichment per symbol) |
| `{name}_agent3.json` | execute rating | Agent 3 output (final rated stocks, sorted) |
| `run.log` | `_run_log()` context manager | Full pipelined log: all `logger.info`/`logger.warning`/`logger.error` calls from every module in the pipeline (Polygon, BO/VCP/EP scanners, enrichment agents, rating agents). Timestamped with module name. Deleted on `FileHandler.close()` when the run completes or fails. Added via `FileHandler` to root logger; removed in `finally` block. Location: `pipeline.py:38`. |