# BO Pipeline — Qullamaggie Breakout Setup Detector

- **Purpose**: Pure-math detector for Kristjan Kullamägi "Qullamaggie Breakout" setups: stocks with extreme prior momentum (impulse ≥ 30% over 20–63d), a tightening 10–40d base (VCI ≤ 0.65), a KDE resistance pivot in the base's upper quartile, higher lows, and a breakout close above pivot with volume surge ≥ 1.5× baseline while price "surfs" the EMA10. Formatted exactly like the VCP pipeline (3 agents, wizard/CLI/pipeline integration identical).
- **Key entry points**: `stock_analyze/cli.py` → `bo`/`bo-scan`/`bo-enrich` subcommands (`cli.py:100,106,112`), `stock_analyze/interactive.py` → "Daily BO scan" pipeline choice, `stock_analyze/pipeline.py` → `run_daily()` dispatches on `pipeline_type="daily_bo_scan"` → `_run_daily_bo()` (`pipeline.py:850`)
- **Depends on**: `tradingview_screener`, `tvDatafeed`/`tradingview_data.batch_get_stock_data`, `pydantic`, `pandas`, `numpy`. Agent 2–3 reuses VCP's `agents/enrichment.py` (Tavily + OpenRouter) and VCP's `apply_vcp_caps`.
- **Depended by**: wizard `_run_auto`/`_run_manual` (`interactive.py`), CLI handlers (`cli.py:268,301,324`), daily run dispatch (`pipeline.py:850`)
- **Version**: 0.3.0 (implemented, full suite green 2026-08-10)

---

## Project Structure (BO additions)

```
stock_analyze/
├── scanners/
│   ├── vcp/                    # VCP Agent 1 (unchanged; shared gates + RS metrics reused)
│   └── bo/                     # NEW: BO Agent 1
│       ├── __init__.py         # Lazy-imports run_bo_scan
│       ├── gates.py            # ADR20 envelope + BO gate + build_bo_rated_stock (reuses VCP caps)
│       ├── metrics.py          # Prior impulse, ADR20, VCI, MA stack/surfing, KDE pivot, higher lows,
│       │                       # volume signature, base detection, breakout trigger, variants, scoring
│       └── runner.py           # run_bo_scan(), merge_bo_force_rows(), _fetch_spy()
├── models/
│   └── bo.py                   # NEW: BoBase, BoSetupRating, BoScanBucket, BoEnrichedBucket,
│                               # BoRatedStock, BoRatedBucket (reuses VcpContextEnrichment)
├── data/
│   └── screener.py             # extended: fetch_us_bo_universe() (same Stage-2 pre-filter, reuses VCP_COLUMNS)
├── pipeline.py                 # extended: execute_bo_scan/enrichment, format_bo_rating_table,
│                               # _run_daily_bo, dispatch on daily_bo_scan
├── interactive.py              # extended: "Daily BO scan" pipeline choice (Auto + Manual)
└── cli.py                      # extended: bo / bo-scan / bo-enrich subcommands
```

---

## Architecture: 3-Agent BO Pipeline (VCP-mirrored)

```
[TradingView Stage 2 Screener]     [Force Include (user paste)]
        |                                    |
        |  close≥10, close>SMA50/200,        |  LLM parse → SymbolKeys
        |  ADV≥$10M, mktcap≥$100M            |  Screener lookup + OHLCV fallback
        |                                    |
        +------ merge_bo_force_rows() -------+
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
              │ S3 base 10–40d, VCI≤0.65,    │
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
              BoScanBucket (5★/4★/3★)  [3★ discarded by passes_bo_gate]
                        |
                        v
        Agent 2 (REUSED VCP): enrich_with_vcp_context → VcpContextEnrichment
        Agent 3: build_bo_rated_stock → apply_vcp_caps (down-only)
        sort (-final_rating, symbol) → BoRatedBucket → {name}_agent3.json
```

---

## Agent 1 — BO Structural Scanner (`scanners/bo/`)

1. `fetch_us_bo_universe()` (`data/screener.py:138`) — identical Stage-2 pre-filter to VCP (`VCP_COLUMNS` reused): close≥10, close>SMA50, close>SMA200, ADV≥$10M, mktcap≥$100M, america market, volume-desc.
2. Force-include: same `fetch_symbols()` + `enrich_with_retry()` OHLCV fallback path as VCP (`pipeline.py:370-406`).
3. `merge_bo_force_rows()` (`scanners/bo/runner.py:27`) — screener row wins on duplicate key; returns (rows, force_set, source=screener|force|hybrid).
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
| Base duration | 10–40 trading days | `BASE_MIN_DAYS=10`, `BASE_MAX_DAYS=40` |
| VCI | ATR5/ATR20 ≤ 0.65 + narrow 3-day range ≤ 0.6·ADR20 | `VCI_MAX=0.65` |
| MA stack / surfing | EMA10>EMA20, EMA50 slope>0, close within 8% of EMA10 | `SURFING_MAX_PCT=8.0` |
| KDE pivot | Gaussian KDE (bandwidth=3% price) over base peaks, mode in upper quartile | `bandwidth_pct=0.03` |
| Higher lows | consecutive higher swing lows into pivot ≥ 1 | `S_HL >= 1` |
| Volume signature | **dual condition (UT-06)**: base-end dry-up ≤ 0.5× baseline **and** breakout surge ≥ 1.5× baseline — both enforced as the volume essential | `DRYUP_MAX=0.5`, `SURGE_MIN=1.5`, `SURGE_STRONG=2.0`, `SURGE_TEXTBOOK=3.0` |
| Extension cap | close > 8% above EMA10 → clamp to 3★ (EC-01); SMA50 distance reported as `sma50_extension_pct` (never a gate) | — |

### `score_bo_setup` edge semantics

- Returns `None` when `len(df) < MIN_BARS` (90) — need 63d impulse + 40d base + buffer.
- Valid data but no base/breakout → 3★.
- 9 "essential" booleans must ALL be true for >3★: `prior_impulse, adr20, base_duration, vci, ma_stack, pivot_kde, higher_lows, dryup, volume_surge` (volume signature is a dual condition — dry-up then surge).
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
| `BoSetupRating` | `:34` | 8 essential boolean params + dry-up + measured pct values + extension/sma50_extension_pct + meta (base/pivot/breakout/rvol10/rs_rating/as_of) + rating Literal[3,4,5] |
| `BoScanBucket` | `:78` | Agent 1 envelope: ratings + five/four/three_star + counts + universe_source + gates_applied |
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

### `stock_analyze/scanners/bo/gates.py`

| Symbol | Line | Role |
|--------|------|------|
| `ADR_LO` / `ADR_HI` | `:9-10` | 4.0 / 12.0 ADR envelope |
| `passes_adr_envelope(adr20)` | `:13` | 4% ≤ ADR ≤ 12% |
| `passes_bo_gate(rating)` | `:18` | rating ≥ 4 survives to enrichment |
| `build_bo_rated_stock(setup, context)` | `:23` | Merge + reuse `apply_vcp_caps` → BoRatedStock |
| `passes_liquidity_gate` / `MIN_ADV_DOLLAR` | re-exported from `scanners/vcp/gates.py` | Shared $10M ADV$ gate |

### `stock_analyze/scanners/bo/runner.py`

| Symbol | Line | Role |
|--------|------|------|
| `merge_bo_force_rows(...)` | `:27` | Screener + force merge; screener wins on duplicate |
| `_fetch_spy()` | `:58` | SPY 300 bars, AMEX → NYSE fallback |
| `run_bo_scan(...)` | `:81` | Full Agent 1: merge→batch OHLCV (or single-fetch fallback)→SPY→liquidity→score→bucket. Accepts `batch_progress` |

### `stock_analyze/pipeline.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `execute_bo_scan(...)` | `:338` | BO Agent 1: screener/force fetch + enrich_with_retry fallback → run_bo_scan → payload + `_counts` |
| `execute_bo_enrichment(...)` | `:484` | BO Agents 2-3: reuse VCP enrichment → BoRatedBucket |
| `format_bo_rating_table(...)` | `:528` | Plain-text table of rated stocks |
| `_run_daily_bo(...)` | `:671` | Full daily run: Agent1→enrich→rate→artifacts, mirrors `_run_daily_vcp` |
| `run_daily()` dispatch | `:850` | `pipeline_type == "daily_bo_scan"` → `_run_daily_bo` |

### `stock_analyze/data/screener.py` (extended)

| Symbol | Line | Role |
|--------|------|------|
| `fetch_us_bo_universe(...)` | `:138` | Stage-2 pre-filter query; reuses `VCP_COLUMNS` + `MIN_ADV_DOLLAR` |

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
| `tests/test_bo_models.py` | 12 | Schema validation, variant/label/rubric |
| `tests/test_bo_metrics.py` | 30 | UT-01..06 indicators + EC-01..06 edge matrix + golden artifacts + variants |
| `tests/test_bo_gates.py` | 17 | ADR envelope, BO gate, lower_base ceiling, caps |
| `tests/test_bo_runner.py` | 9 | merge rows, run_bo_scan with mocked batch OHLCV |
| `tests/test_pipeline_bo.py` | ~7 | RunConfig dispatch, execute_bo_scan/enrichment |
| `tests/test_cli_bo.py` | ~12 | argparse subcommands, help text |

Run: `python -m pytest tests/test_bo_models.py tests/test_bo_metrics.py tests/test_bo_gates.py tests/test_bo_runner.py tests/test_pipeline_bo.py tests/test_cli_bo.py -q`
Full suite: 274 passed, 1 skipped (2026-08-10).

---

## External API / Service Dependencies

| Service | Library | Used By | Env Var | Credits / Cost |
|---------|---------|---------|---------|----------------|
| TradingView Screener | `tradingview-screener>=3.0.0` | `data/screener.py` (BO universe) | `TV_USERNAME`, `TV_PASSWORD` (optional) | Free |
| TradingView OHLCV | `tvDatafeed` / `tradingview_data` | `batch_get_stock_data()`, `_fetch_spy()` | Same | Free |
| Tavily News Search | `tavily-python>=0.5.0` | Agent 2 (reused VCP enrichment) | `TAVILY_API_KEY` | 1,000 free/month |
| OpenRouter LLM | `openai>=2.16` (OpenRouter) | Agent 2 LLM parse + force-include paste parse | `OPENROUTER_API_KEY` | ~$0.003-0.005/call |

---

## Configuration (Environment Variables)

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `TAVILY_API_KEY` | (required) | Agent 2 | Context enrichment dual-query |
| `OPENROUTER_API_KEY` | (required) | Agent 2 + paste parse | LLM context parsing |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | enrichment.py | OpenRouter endpoint |
| `VCP_ENRICHMENT_LLM_MODEL` | `deepseek/deepseek-v4-flash-0731` | enrichment.py | Model for Agent 2 (BO reuses VCP env var) |

---

## User Routes

- **Route A — Auto**: Wizard → Pipeline=BO → optional force paste → name. Screener Stage-2 pre-filter → merge → batch OHLCV + SPY → liquidity gate → BO detect → 4-5★ → Tavily → ranked.
- **Route B — Manual Apply Gate**: paste → "Apply Gate" → structural gate (rating ≥4) → enrich survivors.
- **Route C — Manual Run All**: paste → "Run all pasted" → gates skipped (except liquidity) → all pasted enriched.
- **Route D — CLI `bo-scan`**: Agent 1 only, no Tavily/LLM.
- **Route E — CLI `bo-enrich --input agent1.json`**: re-run enrichment on existing artifact.

Cost/timing mirror VCP (1 screener + 1 SPY + ~250 batch OHLCV + 30-60 Tavily + 15-30 LLM, ~8-10 min auto route).

---

## Edge Cases / Gotchas

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
- **No 4–5★ survivors**: `_run_daily_bo` (`pipeline.py:721`) short-circuits to a completed run with only `agent1.json`, no enrichment.
- **Down-only caps never boost**: reuse of `apply_vcp_caps` means context can only clamp ratings down.
- **Duplicate merge priority**: screener rows beat force rows in `merge_bo_force_rows`.
- **Force-include fallback chain**: symbols missed by the screener go through `enrich_with_retry()` (primary exchange + NASDAQ→NYSE→AMEX→BATS→CBOE); still-missing symbols recorded in `_failed_force` and printed in red — no interactive re-run.
- **Batch OHLCV fallback**: if `batch_get_stock_data` import fails, runner falls back to per-symbol `get_stock_data` single fetches (`runner.py:131-143`).
- **SPY fetch failure** → empty benchmark → all `rs_rating=None`; scoring proceeds (RS optional).
- **Screening core is pure math** — no LLM in Agent 1 (research directive); LLM only in Agent 2 (reused) and force-paste parsing.
