# Guided 5-Phase Scan Flow

- **Purpose**: Replace the component-graph DAG editor with a linear, guided workflow (`Universe → Scanner → Pattern → AI Search → Report`) that reuses the existing backend pipeline (walker, tool registry, SSE, runtime control, preview, presets) unchanged, plus one new OHLCV batch endpoint.
- **Key entry points**: `web/app/flow/page.tsx` → `FlowShell` (`web/components/flow/FlowShell.tsx`) → per-phase components under `web/components/flow/`; backend additions only in `server/app/routes/symbols.py` + `server/app/main.py:17,62`.
- **Depends on**: `web/lib/flow.ts` (state/reducer/persistence), `web/lib/api.ts` (SSE + REST), `web/lib/graph.ts` (`defaultsFor`/`visibleVars`), `stock_analyze.data.polygon.batch_get_stock_data`, `stock_analyze.tools` registry, `server/app/seed.py` daily definitions, `server/app/control.py` confirmation gate.
- **Depended by**: `web/app/page.tsx` (dashboard → "New guided scan" link), `web/app/runs/[id]/page.tsx` (run detail link from Report), `web/app/new/page.tsx` (redirect).

## Architecture

```
/flow (client "use client")
 └─ FlowShell (useReducer + localStorage hydrate)
     ├─ PhaseStepper       — locked/done/active, phase gating (flow.ts:phaseLocked/phaseDone)
     ├─ UniversePhase      1 — paste / snapshot sweep, cost preview via POST /api/runs/preview
     ├─ ScannerPhase       2 — family control + grouped filter rail (visibleVars) + PresetManager + results table
     ├─ PatternPhase       3 — detection summary + OHLCV evidence gallery (ChartCard) — evidence only, no gate
     ├─ SearchPhase        4 — cost gate stats + run + ConfirmationModal on confirm_needed event
     ├─ ReportPhase        5 — ranked table + JSON/CSV export + run detail link + New scan (reset)
     └─ ActivityFeed       SSE stream (useRunEvents) — live "what's happening", collapsed when idle

State: FlowState (flow.ts:7) persisted to localStorage "stock-scan-flow-v1".
Run model: scan run = Universe→Scanner graph (node:sc_1 artifact → output_rows.bucket);
           search run = Universe→Scanner→Search→Report graph (node:r_1 → output_rows.rated,
           fallback merge_table), surviving symbols passed as paste universe.
           zhao + premarket skip AI Search (FAMILY_HAS_SEARCH=false): stepper is 1→2→3→5
           and the scanner bucket IS the report (setReportRows mirrors scanRows).
```

## Zhao + Premarket families (no AI Search)

- **Purpose**: Two scanner families that skip phase 4 (AI Search) — 照妖鏡 (`zhao`, variants `realtime`/`daily`) and `premarket`. The stepper hides phase 4 via `phasesForFamily` (`web/lib/flow.ts`) and the scanner bucket rows are copied into `reportRows` on scan completion so phase 5 works unchanged.
- **Key entry points**: `web/lib/flow.ts` (`Family`, `FAMILY_LABELS`, `FAMILY_PIPELINES`, `FAMILY_HAS_SEARCH`, `phasesForFamily`, `rowExplanation`, `patternOverlay`); `web/components/flow/ScannerPhase.tsx` (`COLUMNS`); backend `stock_analyze/scanners/zhao/*`, `stock_analyze/scanners/premarket/*`, `stock_analyze/pipeline.py:execute_zhao_scan/execute_premarket_scan`, `stock_analyze/tools/builtins.py:_scanner_callable`.
- **Depends on**: Polygon snapshot/OHLCV (`data/polygon.py`), `scan_signals` table + `node_overrides` streak injection (server jobs), `PIPELINE_TYPES` (`server/app/schemas.py:9`).
- **Depended by**: `FlowShell` stepper, `ReportPhase` (no-search copy), `PresetManager` builtin starters, `web/lib/api.ts:PIPELINE_LABELS`.

### Family wiring

| Item | Where | Detail |
|-----|-----|---|
| `Family` union | `web/lib/flow.ts:4` | `"ep" \| "vcp" \| "bo" \| "zhao" \| "premarket"`. |
| `FAMILY_LABELS` | `web/lib/flow.ts:38` | `zhao: "照妖鏡"`, `premarket: "Premarket"`. |
| `FAMILY_PIPELINES` | `web/lib/flow.ts:44` | `zhao → daily_zhao_scan`, `premarket → daily_premarket_scan` (registered in `server/app/schemas.py:PIPELINE_TYPES`). |
| `FAMILY_HAS_SEARCH` | `web/lib/flow.ts:55` | `false` for zhao/premarket; `phasesForFamily` returns `[1,2,3,5]`. |
| `setFamily` reducer | `web/lib/flow.ts:96` | Premarket with no pasted text → `universeSource="snapshot"` (sweep-first default, research 03). |
| `scannerGroups` | `web/lib/graph.ts:25` | `zhao → ["Family","Zhao"]`, `premarket → ["Family","Premarket"]`. |
| `COLUMNS` | `web/components/flow/ScannerPhase.tsx:47` | zhao: symbol, ★(strength), variant, today%, margin, close, SMA20, 52w%, streak, sector. premarket: symbol, name, change%, price, vol, sector, ★. |
| Builtin starters | `web/components/flow/PresetManager.tsx` | `照妖鏡 realtime`, `照妖鏡 daily`, `Premarket grep` (frontend-only until seeded). |
| `PIPELINE_LABELS` | `web/lib/api.ts:94` | Run tables render `照妖鏡` / `Premarket grep`. |

### Backend surface

- `stock_analyze/scanners/zhao/metrics.py` — pure math: `sma20`, `pct_change`, `rel_strength_20d`, `pct_from_high`, `strength_tier_realtime` (5≥3.0 / 4≥1.5 / 3>0 / 2), `strength_tier_daily` (RS+52w composite). The 1/2/3+ streak label lives in the frontend (`streakLabel`, `web/lib/flow.ts`).
- `stock_analyze/scanners/zhao/runner.py:run_zhao_scan` — paste-first; batch OHLCV + benchmark OHLCV; gates per variant (`close>SMA20` always, realtime adds `margin≥min`, daily adds `rs≥min` + `pct_from_high≥-max`); daily ranks by RS desc; `streak = prior + 1` from the `streaks` map.
- `stock_analyze/scanners/premarket/runner.py:run_premarket_scan` — one snapshot call → `change_pct ≥ min` filter → sort desc → cap → tier; pasted symbols bypass the change gate (`force_set`); `select_premarket_candidates` bounds detail/ADV work.
- `stock_analyze/pipeline.py:execute_zhao_scan` / `execute_premarket_scan` — resolve force keys, orchestrate OHLCV / snapshot + `resolve_batch_details` (name/sector via `sic_description`) + optional 20d ADV for the volume flag.
- `server/app/schemas.py:PIPELINE_TYPES` — adds `daily_zhao_scan`, `daily_premarket_scan` (RunCreate validator passes for the graph path).
- `stock_analyze/tools/builtins.py:extract_rating` — includes `strength` so report rows rank by the deterministic tier.

### scan_signals (zhao daily streak)

- `server/app/schema.sql` — `scan_signals(symbol, scan_family, scan_variant, signal_date, PK(symbol,scan_family,scan_variant,signal_date))`.
- `server/app/db.py:Repo` — `record_scan_signals` (idempotent upsert), `get_scan_streaks(symbols, family, variant, as_of)` counting **strictly prior** consecutive dates (today's hit is added by the runner as `prior+1`, so same-day re-runs never inflate).
- `server/app/jobs.py` — `_zhao_daily_scanner_nodes` finds zhao-daily scanner nodes; `_streak_overrides` injects `__streaks__` via `node_overrides` pre-`run_graph`; `_record_zhao_signals` persists survivors post-run (zhao daily only).

## Key Symbols

| Symbol | File:Line | Role |
|-----|-----|---|
| `FlowState` / `FlowAction` | `web/lib/flow.ts:7,20` | Reducer state + action union (incl. `hydrate` for SSR-safe localStorage restore). |
| `flowReducer` | `web/lib/flow.ts:72` | Pure state transitions; `reset` clears, `hydrate` merges over defaults. |
| `loadFlowDraft` / `saveFlowDraft` / `clearFlowDraft` | `web/lib/flow.ts:108-134` | localStorage persistence for reload recovery. |
| `phaseLocked` / `phaseDone` | `web/lib/flow.ts:229,244` | Stepper gating; Report `done` requires `reportRows.length > 0`. |
| `buildScannerGraph` / `buildSearchGraph` | `web/lib/flow.ts:159,180` | Node graphs reused by `POST /api/runs`; search graph = universe+scanner+search+report. |
| `scanRunBody` / `searchRunBody` | `web/lib/flow.ts:205,215` | Run request bodies; search body uses survivors as `force_symbols`. |
| `scannerRowsFromArtifacts` / `reportRowsFromArtifacts` | `web/lib/flow.ts:284,290` | Extract phase rows from `node:sc_1` / `node:r_1` artifacts. |
| `rowRating` / `rowExplanation` / `patternOverlay` | `web/lib/flow.ts:260,317,368` | Rating extraction (incl. `strength`), per-family pass/fail explanations, chart overlay anchors (zhao adds SMA20 line). |
| `FAMILY_HAS_SEARCH` / `phasesForFamily` | `web/lib/flow.ts:55,65` | Family flag + stepper phase list; zhao/premarket skip AI Search (1→2→3→5). |
| `PatternOverlay` / `toChartTime` | `web/lib/flow.ts:359,416` | Price lines + markers; ISO datetime → `YYYY-MM-DD` chart time. |
| `fetchOhlcv` | `web/lib/api.ts:130` | POST `/api/ohlcv`, returns `{symbol: OhlcvBar[]}`. |
| `subscribeToRunEvents` / `controlRun` | `web/lib/api.ts:48,150` | SSE subscription (auto-close on terminal events); skip/pause/resume/cancel/confirm. |
| `useRunEvents` | `web/lib/runEvents.ts` | Hook: `{events, terminal, error}`; terminal ∈ idle/running/succeeded/failed/cancelled. |
| `ChartCard` | `web/components/flow/ChartCard.tsx` | lightweight-charts candlesticks + volume + `createSeriesMarkers` markers + price lines (v5 plugin API). |
| `ConfirmationModal` | `web/components/ConfirmationModal.tsx` | proceed/skip/cancel for the runtime `confirm_needed` gate. |
| `ohlcv_batch` | `server/app/routes/symbols.py` | `POST /api/ohlcv` (bars 30–500, default 300) wrapping `batch_get_stock_data` via `asyncio.to_thread`. |
| `base_start_idx` / `base_end_idx` | `stock_analyze/models/bo.py` | BO base bar anchors populated in `score_bo_setup` (`scanners/bo/metrics.py`). |

## Backend surface

- `POST /api/ohlcv` (`server/app/routes/symbols.py`): body `{symbols: [{symbol, exchange}], bars?}` → `batch_get_stock_data(pairs, n_bars=bars)` → `{symbols: {SYM: [{datetime, open, high, low, close, volume}]}}`; failed symbols → `[]`.
- `POST /api/runs/preview`, `POST /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/events`, `POST /api/runs/{id}/control`, `GET /api/tools`, `GET /api/definitions`, `GET/POST/DELETE /api/component-templates` — all pre-existing, unchanged; the flow is a new frontend client of them.

## Design system

- `web/tailwind.config.ts`: charcoal `ink` neutrals (950–500), amber `accent`, semantic `up`/`down`; fonts Instrument Sans (UI) + IBM Plex Mono (data/tnum).
- `web/app/globals.css`: `.panel`, `.field`, `.btn`/`.btn-primary`/`.btn-ghost`/`.btn-danger`, `.label`, `.tnum`; thin dark scrollbars; `color-scheme: dark`.
- `web/app/layout.tsx`: fontsource CSS imports + font-mono/sans classes on `body`.

## Edge Cases / Gotchas

- **SSR hydration**: `loadFlowDraft()` reads `window` — must be called in a `useEffect` (`hydrate` action), not in the reducer initializer, to avoid server/client mismatch.
- **Save-after-hydrate**: the persistence effect is gated on `hydrated`, otherwise the initial state would clobber the stored draft on mount.
- **lightweight-charts v5**: `series.setMarkers()` no longer exists — use `createSeriesMarkers(series, markers)` and `markers.detach()` on cleanup.
- **Chart time**: lightweight-charts requires business-day `YYYY-MM-DD` strings; `toChartTime` slices the ISO datetime.
- **`breakout_idx` bounds**: overlay code guards `bi < bars.length`; out-of-range indices are dropped silently.
- **Artifact typing**: `output_rows.bucket/rated` are `unknown[]` in TS — cast to `Record<string, unknown>[]` after `Array.isArray`; `reportRows` fall back to `merge_table.rows`.
- **Downstream invalidation**: changing universe source/text or scanner family clears scan/search runs and rows via `clearResults` / `selectFamily` so stale survivors don't leak into later phases.
- **No-search report rows**: for zhao/premarket, `ScannerPhase` mirrors the scanner bucket into `reportRows` on success; `ReportPhase` copy swaps "AI enrichment" wording based on `FAMILY_HAS_SEARCH`.
- **Premarket universe default**: `setFamily("premarket")` with no pasted text flips `universeSource` to `snapshot`; a pasted watchlist keeps paste mode.
- **`confirm_needed` handling**: `SearchPhase` watches the last SSE event for `type === "confirm_needed"` and raises `ConfirmationModal`; `controlRun(id, "confirm", node_id, decision)` resolves it.
- **Activity feed**: auto-collapses when `runId` is null (idle phases); the SSE hook keeps only the last 300 events.
- **`/new` redirect**: `web/app/new/page.tsx` is a thin `redirect("/flow")`; `ScanForm.tsx`, `GraphEditor.tsx`, and `web/app/editor/page.tsx` were deleted.
