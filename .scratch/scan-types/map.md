# Scan Types — 照妖鏡 (realtime + daily) + Premarket grep — Spec Map

## Destination

Spec-plus-build of two new scanner families in the guided flow, grounded in Ah Ju's trading principles:

- **zhao (照妖鏡)** — two variants via a `zhao_variant` var: `realtime` ("strong stocks on a weak day", no market-regime gate, benchmark context banner) and `daily` (EOD relative-strength scan: `close > SMA20`, positive 20d RS vs SPY, within 15% of 52w high, ranked by RS desc, `scan_signals` streak persistence). Paste-first universe (market sweep available). No AI Search.
- **premarket (grep)** — single snapshot call at run time; filter premarket % change vs prior close (default >5%); universe = sweep-first + paste + survivor cap (research 03 resolved). No AI Search.

Both families feed the deterministic 1–5 strength tier into `rowRating`/`extract_rating` so Report integrates unchanged.

## Notes

- Domain: scanner family mechanism — `stock_analyze/tools/variables.py:17` (`SCANNER_VARS`) + `:70` (`SCANNER_GROUPS`), dispatch `stock_analyze/tools/builtins.py:86` (`_scanner_callable`), metrics-layer precedent `stock_analyze/scanners/bo/` + `models/bo.py`, execute fns in `stock_analyze/pipeline.py`, frontend `web/lib/flow.ts:4` (`Family`, `FAMILY_LABELS`, graph builders), `web/lib/graph.ts:25` (`scannerGroups`), `web/components/flow/ScannerPhase.tsx` (family buttons + COLUMNS).
- Data layer: `stock_analyze/data/polygon.py` — `fetch_market_snapshot` (`:274`, one all-tickers call; `change_pct` = `todays_change_percent`, includes premarket from 4am ET), `fetch_spy`/`get_stock_data` OHLCV, `resolve_force_symbol` (`:241` needs `sic_description` one-line addition), `batch_get_stock_data` (`:171`).
- Persistence: `server/app/db.py` `Repo` + `server/app/schema.sql` gain a `scan_signals` table (EOD-only writes for zhao daily; streak count 1/2/3+). Streak read/write hooks live in `server/app/jobs.py` `run_graph_job` (async, injected via `node_overrides`, avoiding sync DB in the core library).
- AI Search omission: flow skips phase 4 (stepper 1→2→3→5); Report phase runs `Universe → Scanner → Report` (sc_1 `bucket` scan_rows → r_1 `structural` report_rows is legal per `INPUT_ACCEPTS` `web/lib/graph.ts:4`).
- Tracker: local markdown (`.scratch/scan-types/`), matching `.scratch/ep-scan-enhancement/` precedent.
- Skills: `/grilling` (tickets 01–02, resolved), `/research` (ticket 03, resolved), `/task` (04–05), `frontend-design`.

## Already-settled decisions (grilling rounds 1–3, user confirmed)

- **Family model**: two new family entries — `zhao` (variant var `realtime`|`daily`) and `premarket`; two starter presets "照妖鏡 realtime" / "照妖鏡 daily".
- **照妖鏡 realtime**: no market-regime gate (manual trigger); banner shows benchmark context (today% + vs SMA20) but never blocks. Keep rule `close > SMA20 AND stock today% > benchmark today%`; thresholds editable. Benchmark = `zhao_benchmark` select (SPY|QQQ, default SPY). Sector via Polygon `sic_description`. Strength = margin over market.
- **照妖鏡 daily (EOD)**: `close > SMA20`, 20d RS vs benchmark > 0, close within 15% of 252-day high, ranked by RS desc; thresholds editable. Persistence via `scan_signals` (EOD-only writes; streak 1/2/3+). Strength = RS + 52w proximity composite.
- **Universe**: zhao variants paste-first (sweep available, not preferred). Realtime data path = one all-tickers snapshot joined for today% + batch OHLCV for SMA20. EOD = paste + batch OHLCV for RS/52w/SMA20.
- **AI Search omission**: no Tavily/LLM for zhao/premarket; stepper 1→2→3→5; ReportPhase machinery unchanged (`Universe → Scanner → Report` graph is legal).
- **Premarket**: single snapshot call at run time; filter premarket % change vs prior close (default >5%, editable); universe = sweep-first + paste + survivor cap (research 03: snapshot day bar includes premarket from 4am ET — confirmed).
- **Rating**: deterministic 1–5 strength tier per variant feeds `rowRating`/`extract_rating`.

## Frontier (tickets)

- [照妖鏡 feature definitions (grilling — RESOLVED)](issues/01-zhao-grilling.md) — settled spec above.
- [Premarket feature definitions (grilling — RESOLVED)](issues/02-premarket-grilling.md) — settled spec above.
- [Polygon premarket data verification (research — RESOLVED)](issues/03-polygon-premarket-research.md) — snapshot `day` bar includes premarket; `todaysChangePerc` = premarket % change intraday; 1-call market-wide grep; universe default = sweep-first + paste + cap.
- [照妖鏡 build (task)](issues/04-zhao-build-task.md) — backend family + `scan_signals` streak + UI + tests.
- [Premarket grep build (task)](issues/05-premarket-build-task.md) — snapshot-first universe + UI + tests.

Blocking: 01 → 04; 02/03 → 05.

## Out of scope

- Tavily/LLM enrichment for the new families (deferred).
- Premarket tracked-window (8:45–9:00) semantics (user chose single-call).
- Sector via anything other than Polygon `sic_description`.
- Changing FlowState/run semantics beyond the `hasSearch` family flag.
