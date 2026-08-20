# Premarket grep build task

Depends on: 02-premarket-grilling (RESOLVED), 03-polygon-premarket-research (RESOLVED). Unblocks: tests + consolidate.

## 1. Backend core (metrics + models)

- `stock_analyze/scanners/premarket/metrics.py` — pure functions:
  - `premarket_change_pct(snapshot_change_pct) -> float` (pass-through, documented semantics from research 03).
  - `volume_flag(volume, adv_20d, min_mult) -> bool` (volume ≥ min_mult × adv; adv=0 → False).
  - `strength_tier(change_pct) -> int` (5 ≥ 10.0, 4 ≥ 7.5, 3 ≥ 5.0, else 2).
- `stock_analyze/models/premarket.py` — `PremarketFeatures` (symbol, name, change_pct, price, volume, sector, adv_20d, vol_flag), `PremarketGateThresholds` (min_change_pct default 5.0, min_vol_mult default 0.0, cap default 300), `PremarketScanBucket`.

## 2. Data layer

- `stock_analyze/data/polygon.py` — reuse `fetch_market_snapshot` (`:274`); expose `name` + `sic_description` on the snapshot record if not already; add `adv_20d(symbols)` helper via `batch_get_stock_data` for the volume flag (only for survivors, capped).

## 3. Dispatch + vars + pipeline

- `stock_analyze/tools/variables.py` — `premarket` group + vars: `premarket_min_change_pct` (default 5.0), `premarket_min_vol_mult` (default 0), `premarket_cap` (default 300).
- `stock_analyze/tools/builtins.py` — `_scanner_callable` → `run_premarket_scan` when family==premarket.
- `stock_analyze/scanners/premarket/runner.py` — `run_premarket_scan(params)`:
  1. One snapshot call (full market).
  2. Filter `change_pct ≥ min_change_pct`; sort desc; cap to `cap`.
  3. Union pasted symbols (already in universe resolution).
  4. For survivors with `min_vol_mult > 0`: batch 20d ADV, flag.
  5. Return bucket with per-symbol strength tier + columns.
- `stock_analyze/pipeline.py` — `execute_premarket_scan` (mirrors `execute_ep_scan` shape; snapshot-first, no per-symbol OHLCV fan-out except ADV).

## 4. Frontend

- `web/lib/flow.ts` — `FAMILY_LABELS["premarket"]="Premarket"`; `hasSearch=false`; `buildScannerGraph` handles premarket; `rowExplanation` for change%/strength; universe phase default = sweep for premarket (per research 03 default).
- `web/components/flow/ScannerPhase.tsx` — family button + COLUMNS (`symbol, name, change%, price, vol, sector, ★`).
- `web/components/flow/PresetManager.tsx` — "Premarket grep" starter preset.
- `web/lib/types.ts` — `pipeline_type` accepts `premarket`.

## 5. Tests

- `server/tests/core/test_premarket_scan.py` — strength tiers, vol flag, cap+filter math on a fake snapshot.
- `web/__tests__/` — premarket family no-search stepper, rowRating.
