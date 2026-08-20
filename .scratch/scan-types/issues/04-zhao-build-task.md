# 照妖鏡 (zhao) build task

Depends on: 01-zhao-grilling (RESOLVED). Unblocks: tests + consolidate.

## 1. Backend core (metrics + models)

- `stock_analyze/scanners/zhao/metrics.py` — pure functions:
  - `sma20(close_series) -> float` (last value; trailing 20).
  - `today_pct(overnight_or_intraday) ` handled by data layer; keep metrics stateless: `market_margin(today_pct, bench_pct) -> float`.
  - `rel_strength_20d(stock_series, bench_series) -> float` = (stock_close/lag20 − 1) − (bench_close/lag20 − 1), in %.
  - `pct_from_high(close, high_252) -> float` (negative = below high, in %).
  - `strength_tier_realtime(margin_pct) -> int` (5 ≥ 3.0, 4 ≥ 1.5, 3 > 0, else 2).
  - `strength_tier_daily(rs_pct, pct_from_high) -> int` (5: rs≥10 ∧ high_dist≤5; 4: rs≥5 ∧ high_dist≤10; 3: survivor; 2: else).
  - `streak_class(days: int) -> str` = "1" | "2" | "3+".
- `stock_analyze/models/zhao.py` — `ZhaoSetupFeatures` (symbol, close, sma20, today_pct, bench_pct, margin, rs_20d, pct_from_high, sector, volume_adv, streak), `ZhaoStock`, `ZhaoGateThresholds` (sma20_buffer_pct, min_margin_pct, min_rs_pct, max_high_dist_pct, sma20_window, high_window), `ZhaoScanBucket` (variant, rows, params, bench).

## 2. Data layer

- `stock_analyze/data/polygon.py` — add `sic_description` to `resolve_force_symbol` (`:241`) return dict; expose on snapshot/OHLCV fetch paths used by zhao.

## 3. Dispatch + vars + pipeline

- `stock_analyze/tools/variables.py` — add `zhao` group + vars: `zhao_variant` (select realtime|daily), `zhao_benchmark` (select SPY|QQQ), `zhao_sma20_buffer_pct` (default 0), `zhao_min_margin_pct` (default 1.0), `zhao_min_rs_pct` (default 0), `zhao_max_high_dist_pct` (default 15).
- `stock_analyze/tools/builtins.py` — `_scanner_callable` (`:86`) → `run_zhao_scan` when family==zhao.
- `stock_analyze/scanners/zhao/runner.py` — `run_zhao_scan(universe, params) -> dict`: resolve symbols (paste-first; snapshot sweep optional), fetch OHLCV batch, compute metrics per variant, filter gates, rank (daily: RS desc), return buckets + strength + streak.
- `stock_analyze/pipeline.py` — `execute_zhao_scan` mirroring `execute_ep_scan`/`execute_bo_scan` (fan-out via batch_get_stock_data; yields per-symbol results to the graph-walker contract used by builtins `_scanner_callable`).

## 4. Persistence (streak) — async seam in jobs, not core lib

- `server/app/schema.sql` + `server/app/db.py` — `scan_signals(symbol text, scan_family text, scan_variant text, signal_date date, PRIMARY KEY (symbol, scan_family, scan_variant, signal_date))`.
- `server/app/db.py` `Repo` — `record_scan_signals`, `get_scan_streaks(symbols, family, variant)` (count consecutive dates ending today).
- `server/app/jobs.py` — `run_graph_job`: post-run, for zhao daily only, `await`-injectable callback via `node_overrides` writing rows and attaching `streak` to each row before it reaches Report. Keep core lib DB-free.

## 5. Frontend

- `web/lib/flow.ts` — add `Family = ... | "zhao" | "premarket"`; `FAMILY_LABELS["zhao"]="照妖鏡"`; extend `scannerGroups` (`web/lib/graph.ts:25`) for zhao vars; `buildScannerGraph` handles zhao (variant var drives sc_1 family param); `rowExplanation`, `patternOverlay` (SMA20 line) for zhao; `hasSearch=false` wiring so stepper is 1→2→3→5.
- `web/components/flow/ScannerPhase.tsx` — family buttons + variant toggle + COLUMNS for zhao (`symbol, ★, variant, today%, margin, close, SMA20, 52w%, streak, sector`).
- `web/components/flow/PresetManager.tsx` — two zhao starter presets.
- `web/lib/types.ts` — `pipeline_type` accepts `zhao`.

## 6. Tests

- `server/tests/core/test_zhao_scan.py` — metrics units + runner buckets (realtime gate math, daily RS ranking, streak tier).
- `server/tests/test_jobs.py` or `test_symbols.py`-adjacent — `scan_signals` record/streak via `Repo`.
- `web/__tests__/` — flow reducer: zhao family produces no-search stepper (1→2→3→5), zhao rowRating/explanation.
