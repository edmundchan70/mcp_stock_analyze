# 照妖鏡 (zhao) — Feature Definitions (grilling, RESOLVED)

Status: **RESOLVED** (grilling rounds 1–3, user confirmed). Blocks: 04-zhao-build-task.

## Confirmed decisions

### Family model
- New family `zhao` with variant var `zhao_variant` ∈ `["realtime", "daily"]` (default `realtime`).
- Two starter presets: "照妖鏡 realtime", "照妖鏡 daily".
- Both variants paste-first (market sweep available but not preferred).

### realtime ("strong stocks on a weak day")
- **No market-regime gate** — user triggers manually any time; benchmark context is a banner, never a block.
- **Keep rule**: `close > SMA20` (with editable min-% buffer) **AND** `stock today% > benchmark today%` (with editable min margin %). Both thresholds are scanner vars.
- **Benchmark**: `zhao_benchmark` select var (SPY|QQQ, default SPY).
- **Data path**: one all-tickers Polygon snapshot call joined against universe symbols for today%, + batch daily OHLCV for SMA20.
- **Sector**: Polygon `sic_description` (add to `resolve_force_symbol` return).
- **Strength tier**: margin over market — `today_pct − benchmark_pct`; deterministic 1–5 (5 ≥ +3.0%, 4 ≥ +1.5%, 3 > 0).

### daily (EOD relative strength)
- **Keep rule**: `close > SMA20` (editable buffer) **AND** 20d RS vs benchmark > 0 (editable min) **AND** `close` within 15% of 252-day high (editable max distance). All thresholds scanner vars.
- **Rank**: by 20d RS vs benchmark desc.
- **Persistence**: `scan_signals` DB table, EOD-only writes; streak count 1/2/3+ (consecutive days appearing, ending today).
- **Strength tier**: RS + 52w proximity composite (5 = RS ≥ +10% AND within 5% of high; 4 = RS ≥ +5% AND within 10%; 3 = survivor).

### Output columns (Scanner results table)
`symbol, ★ (strength), variant, today% / RS, margin, close, SMA20, 52w prox %, streak, sector`.

### Chart overlay (Pattern phase)
SMA20 price line + last-bar marker; nothing else.

### AI Search
Omitted (no Tavily/LLM). Flow stepper 1→2→3→5; Report runs `Universe → Scanner → Report`.

## Open (deferred / out of scope)
- Sector via anything other than Polygon `sic_description`.
- Intraday-vs-EOD shared code beyond the metrics layer.
