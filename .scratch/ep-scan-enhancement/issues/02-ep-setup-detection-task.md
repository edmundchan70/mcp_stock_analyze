# Ticket 02 — `score_ep_setup` + `EpSetupFeatures` (task)

## Deliverable

1. `stock_analyze/scanners/ep/setup.py` — pure-math EP technical layer:
   - `EpSetupThresholds` (pydantic): `spike_min=3.0`, `pullback_vol_ratio=0.5`, `pullback_depth_pct=10.0`, `ema_touch_pct=2.0`, `vwap_touch_pct=1.5`, `base_min_days=5`, `base_max_days=40`.
   - `FEATURE_KEYS = ["base_detected", "volume_spike", "pullback_contrast", "ema_support", "vwap_support"]`.
   - `score_ep_setup(df, *, enabled=None, thresholds=None, symbol="", exchange="") -> EpSetupFeatures`.
   - Helpers: `_event_idx` (highest-volume bar in last 63), `_post_window` (first `base_max_days` bars after event), `_detect_base`, `_detect_pullback`, `_detect_ema_support`, `_detect_vwap` (+ `_anchored_vwap`).
   - Reuses from `scanners/bo/metrics.py`: `find_local_peaks` (:154), `find_local_lows` (:208), `higher_lows` (:220).
   - `features_held` = count of **enabled** features that hold (defaults to all enabled when `enabled` is empty → but runner only enables feature mode when ≥1 toggle on).

2. `stock_analyze/models/ep.py` — new `EpSetupFeatures` schema:
   - `event_idx: Optional[int]`, 5 feature booleans (default False), `features_held: int = 0`, measured values `event_volume_ratio`, `pullback_vol_ratio`, `ema_stack_aligned`, `vwap_anchor: Literal["event","pivot","none"] = "none"`.

3. Tests — `server/tests/core/test_ep_setup.py`:
   - Synthetic OHLCV fixtures (event-shock → base → recovery), mirroring `server/tests/core/bo_fixtures.py`.
   - Pass/fail per feature; keep-if-any boundary; per-feature toggles; `enabled` gating of `features_held`; `df=None` → all-False.

## Seams

- `score_ep_setup` is called from `scanners/ep/runner.py:run_ep_scan` (ticket 03). It must never raise on malformed/short frames — return all-False features.
- `EpSetupFeatures` fields serialize into `EpStock` (ticket 03) — no NaN/Inf; use float defaults.
