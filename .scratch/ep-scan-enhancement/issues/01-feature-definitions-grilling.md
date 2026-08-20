# Ticket 01 — Feature Definitions + Thresholds (grilling)

**Status**: proposed → user confirms or adjusts per-feature before build.

Common context: **event day** = highest-volume bar in the last 63 bars (`_event_idx` in `scanners/ep/setup.py`, planned); **base** = consolidation after it. All thresholds live in one constants block (`EpSetupThresholds`) and are editable as scanner vars (`tools/variables.py`).

## Feature proposals

1. **base_detected** — post-event window (5–40 bars) has a valid base: a pivot (reuse `find_local_peaks` from `scanners/bo/metrics.py:154`), ascending swing structure (≥1 strictly-higher low via `higher_lows`, `scanners/bo/metrics.py:220`), and volume contrast (pullback bars ≤ 0.5× event volume, up-leg ≥ 1.5× pullback avg). Defaults: `base_min_days=5`, `base_max_days=40`, `pullback_vol_ratio=0.5`.
2. **volume_spike** — event-day volume ≥ `spike_min` × the 50-day average before the event (default `3.0`).
3. **pullback_contrast** — post-event high → low drawdown ≥ `pullback_depth_pct` (default `10.0%`), the high→low leg's avg volume ≤ `pullback_vol_ratio` × event volume, and last close above the pullback low (recovery).
4. **ema_support** — price above EMA9/EMA20/EMA50 with stack ordered (EMA9>EMA20>EMA50) and ≥ 2 of the 3 EMAs touched-and-held since the event (bar low within `ema_touch_pct` (default `2.0%`) of the EMA, close back above).
5. **vwap_support** — anchored VWAP from the event day first; if no support, fall back to the post-event pivot (higher high) anchor; holds when a bar low dipped within `vwap_touch_pct` (default `1.5%`) of VWAP with close back above, and current close > VWAP. `vwap_anchor` records which anchor showed support (`event` | `pivot` | `none`).

## Keep rule

`features_held` = count of **enabled** held features. Survive if `features_held ≥ 1` (`ep_keep_if_any=True`), or if `features_held == enabled_count` when `ep_keep_if_any=False`.

## Open questions for the user

- Should `features_held` still include disabled features for display, or strictly count enabled-only?
- `ep_keep_if_any=False` semantics: require ALL enabled features, or a different threshold?
- VWAP fallback anchor: pivot (base high) vs base low (higher low)?
