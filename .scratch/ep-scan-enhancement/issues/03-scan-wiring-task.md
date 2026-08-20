# Ticket 03 — Scan wiring + scanner vars (task)

## Deliverable

1. `stock_analyze/scanners/ep/runner.py`
   - `run_ep_scan(...)` gains `ep_features: bool = False` and `ep_feature_keys: tuple[str, ...] = ()` + `ep_keep_if_any: bool = True` (plus threshold overrides via `EpSetupThresholds`).
   - Per symbol: pass the per-symbol OHLCV `df` into `score_ep_setup`; fold the resulting features/booleans into the row.
   - Survivor rule: when `ep_features` and ≥1 key enabled → **keep if `features_held ≥ 1`** (or all-enabled when `keep_if_any=False`); Baseline/Strict still computed and attached but no longer filter.
   - `merge_force_rows` must not drop feature fields on force rows.

2. `stock_analyze/models/ep.py` — extend `EpStock` with the 5 feature booleans + `features_held` + `measured` fields (`event_volume_ratio`, `pullback_vol_ratio`, `ema_stack_aligned`, `vwap_anchor`).

3. `stock_analyze/pipeline.py:execute_ep_scan` — accept `df_by_symbol` (per-symbol OHLCV from the data layer), forward to `run_ep_scan`, and pass EP technical params from `SCANNER_VARS`.

4. `stock_analyze/tools/variables.py` — new `SCANNER_GROUPS["ep_technical"]` with vars: `ep_features_enabled` (bool, default True), `ep_keep_if_any` (bool), 5 × `ep_feature_<key>` toggles (default True), and editable thresholds `ep_spike_min`, `ep_pullback_vol_ratio`, `ep_pullback_depth_pct`, `ep_ema_touch_pct`, `ep_vwap_touch_pct`, `ep_base_min_days`, `ep_base_max_days`.

5. `stock_analyze/tools/builtins.py:_scanner_callable` — read the new vars and forward them; include feature booleans in the returned row dicts.

## Verification

- `server/tests/core/test_builtin_search.py`, `server/tests/test_jobs.py`, `server/tests/test_symbols.py` updated/extended.
- One new end-to-end test: scan with EP features ON vs OFF → feature-mode keeps a stock gates would drop.
