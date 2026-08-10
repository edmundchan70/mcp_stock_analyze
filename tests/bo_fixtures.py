"""Deterministic synthetic OHLCV scenario builders for BO tests.

No random walks — every series is a deterministic phase sequence
(impulse → base → breakout) so golden artifacts are reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Scaling factor so that a full 20-day base's mean daily range ≈ adr_pct.
# base_mean_range ≈ imp_range * (1 + base_down) / 2; with base_down=0.25 the
# factor 1 / 0.625 ≈ 1.6 makes the measured ADR20 equal adr_pct.
_IMPULSE_RANGE_FACTOR = 1.6


def _base_down_for_vci(vci_target: float, n_base: int) -> float:
    """Solve base range decay so VCI (ATR5/ATR20 over the base) ≈ target."""
    def _vci_for(d: float) -> float:
        seq = np.linspace(1.0, d, n_base)
        return float(seq[-5:].mean() / seq.mean())

    lo, hi = 0.1, 0.6
    for _ in range(48):
        mid = (lo + hi) / 2
        if _vci_for(mid) > vci_target:
            hi = mid
        else:
            lo = mid
    return float((lo + hi) / 2)


def _bars_from_closes(closes, ranges, volumes, seed=7):
    """Build OHLC from closes + range fractions (deterministic tiny noise)."""
    rng = np.random.default_rng(seed)
    n = len(closes)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    for i in range(n):
        c = closes[i]
        half = c * ranges[i] / 2.0
        highs[i] = c + half
        lows[i] = c - half
        opens[i] = lows[i] + (highs[i] - lows[i]) * rng.uniform(0.3, 0.7)
    return opens, highs, lows


def _make_bo_series(
    *,
    impulse_pct: float = 50.0,
    adr_pct: float = 6.0,
    base_duration: int = 20,
    vci: float = 0.5,
    breakout_surge: float = 3.0,
    surfing_dist: float = 5.0,
    proximity_52w: float | None = None,
    volume_dryup: float = 0.4,
    impulse_bars: int = 70,
    pullback_pct: float = 2.0,
    breakout_bars: int = 5,
    decay: bool = True,
    seed: int = 7,
) -> pd.DataFrame:
    """Build a deterministic impulse → base → breakout series.

    Args:
        impulse_pct: prior impulse gain (%%).
        adr_pct: target 20-day ADR %% (measured at base end ≈ this value).
        base_duration: consolidation length in bars.
        vci: target ATR(5)/ATR(20) ratio at base end.
        breakout_surge: breakout-day volume relative to pre-base baseline.
        surfing_dist: final breakout close %% above the base center.
        volume_dryup: base-end volume relative to pre-base baseline.
        impulse_bars: length of the prior impulse.
        pullback_pct: base pullback %% below the impulse peak.
        breakout_bars: bars after the base ends.
        decay: whether base daily ranges decay (False → stale flat base).
        seed: deterministic noise seed.
    """
    peak = 100.0 * (1.0 + impulse_pct / 100.0)
    n = impulse_bars + base_duration + breakout_bars

    closes = np.zeros(n)
    volumes = np.ones(n) * 1_000_000

    # Impulse: linear advance 100 → peak.
    closes[:impulse_bars] = np.linspace(100.0, peak, impulse_bars)

    imp_range = adr_pct / 100.0 * _IMPULSE_RANGE_FACTOR
    base_center = peak * (1.0 - pullback_pct / 200.0)

    if decay:
        base_down = _base_down_for_vci(vci, base_duration)
    else:
        base_down = 1.0

    # Base: touch a horizontal resistance R every 3rd bar; lows ascend.
    R = base_center * (1.0 + 0.35 * imp_range)
    tight = imp_range * np.linspace(1.0, base_down, base_duration)
    for j in range(base_duration):
        touch = (j % 3 == 0) or (j == base_duration - 1)
        c = R - tight[j] * base_center * (0.5 if touch else 0.75)
        closes[impulse_bars + j] = c
        volumes[impulse_bars + j] = 1_000_000 * np.linspace(0.9, volume_dryup, base_duration)[j]

    # Breakout: closes advance from base center to (surfing_dist %% above it).
    brk_closes = np.linspace(
        base_center, base_center * (1.0 + surfing_dist / 100.0), breakout_bars,
    )
    closes[impulse_bars + base_duration:] = brk_closes
    volumes[impulse_bars + base_duration:] = 1_000_000 * breakout_surge

    ranges = np.full(n, imp_range)
    for j in range(base_duration):
        ranges[impulse_bars + j] = tight[j]

    opens, highs, lows = _bars_from_closes(closes, ranges, volumes, seed=seed)

    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _base_bars(base_center, n_base, imp_range, base_down, volume_dryup):
    """Base bars touching a horizontal resistance with decaying ranges."""
    tight = imp_range * np.linspace(1.0, base_down, n_base)
    R = base_center * (1.0 + 0.35 * imp_range)
    closes = []
    for j in range(n_base):
        touch = (j % 3 == 0) or (j == n_base - 1)
        closes.append(R - tight[j] * base_center * (0.5 if touch else 0.75))
    volumes = 1_000_000 * np.linspace(0.9, volume_dryup, n_base)
    return np.asarray(closes), tight, np.asarray(volumes)


def _make_lower_base_series(
    *,
    impulse_pct: float = 50.0,
    adr_pct: float = 6.0,
    vci: float = 0.5,
    breakout_surge: float = 2.0,
    volume_dryup: float = 0.3,
    seed: int = 11,
) -> pd.DataFrame:
    """Two-base sequence: base A (higher high) → continuation → shallower base B.

    Final close clears base B's high but stays below the continuation top.
    volume_dryup models supply dry-up in BOTH bases (0.3 → measured ratio ≤ 0.5
    even with the full-volume continuation bars inflating base B's baseline).
    """
    peak = 100.0 * (1.0 + impulse_pct / 100.0)
    imp_range = adr_pct / 100.0 * _IMPULSE_RANGE_FACTOR
    n_base = 20
    base_down = _base_down_for_vci(vci, n_base)

    n1 = 50  # impulse 1
    nA = 20  # base A
    ncont = 12  # continuation to higher high
    nB = 20  # base B
    total = n1 + nA + ncont + nB + 2

    closes = np.zeros(total)
    volumes = np.ones(total) * 1_000_000
    ranges = np.full(total, imp_range)

    closes[:n1] = np.linspace(100.0, peak, n1)

    # Base A below the impulse peak.
    ca, ta, va = _base_bars(peak * 0.985, nA, imp_range, base_down, volume_dryup)
    closes[n1:n1 + nA] = ca
    volumes[n1:n1 + nA] = va
    ranges[n1:n1 + nA] = ta

    # Continuation to the higher high (clears base A).
    cont_top = peak * 1.06
    closes[n1 + nA:n1 + nA + ncont] = np.linspace(peak * 1.01, cont_top, ncont)

    # Base B below the continuation top, shallower.
    cb, tb, vb = _base_bars(cont_top * 0.965, nB, imp_range, base_down, volume_dryup)
    closes[n1 + nA + ncont:n1 + nA + ncont + nB] = cb
    volumes[n1 + nA + ncont:n1 + nA + ncont + nB] = vb
    ranges[n1 + nA + ncont:n1 + nA + ncont + nB] = tb

    # Breakout: close above base B's high (R_B) but below the continuation top.
    r_b = (cont_top * 0.965) * (1.0 + 0.35 * imp_range)
    closes[-2:] = [r_b * 0.99, r_b * 1.015]
    volumes[-2:] = 1_000_000 * breakout_surge

    opens, highs, lows = _bars_from_closes(closes, ranges, volumes, seed=seed)

    idx = pd.date_range("2024-01-01", periods=total, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _make_garbage_series(n: int = 150, *, seed: int = 42) -> pd.DataFrame:
    """Random walk with random volumes — must never rate above 3★."""
    rng = np.random.default_rng(seed)
    closes = 100.0 + np.cumsum(rng.normal(0.0, 1.2, n))
    ranges = np.abs(rng.normal(0.03, 0.01, n))
    volumes = rng.uniform(200_000, 2_000_000, n)
    opens, highs, lows = _bars_from_closes(closes, ranges, volumes, seed=seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _make_no_base_series(n: int = 130, *, seed: int = 3) -> pd.DataFrame:
    """Monotonic rise with no consolidation — no base ever forms."""
    rng = np.random.default_rng(seed)
    closes = np.linspace(100.0, 170.0, n)
    ranges = np.full(n, 0.05)
    volumes = np.full(n, 1_500_000.0)
    opens, highs, lows = _bars_from_closes(closes, ranges, volumes, seed=seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _make_vshape_series(*, seed: int = 13) -> pd.DataFrame:
    """V-shaped rebound: base then sharp crash then 2-bar recovery above pivot.

    EMA10 stays below EMA20 at the end (EC-04).
    """
    base = _make_bo_series(seed=seed, breakout_bars=0)
    closes = list(base["close"].values)
    volumes = list(base["volume"].values)
    high = max(closes)
    bc = closes[-1]
    crash = [bc * (1.0 - 0.03), bc * (1.0 - 0.06), bc * (1.0 - 0.09),
             bc * (1.0 - 0.11), bc * (1.0 - 0.12)]
    recovery = [bc * (1.0 - 0.05), bc * 1.05]
    closes += crash + recovery
    volumes += [1_000_000] * 5 + [3_000_000] * 2
    n = len(closes)
    ranges = np.full(n, 0.06)
    opens, highs, lows = _bars_from_closes(np.asarray(closes), ranges, np.asarray(volumes), seed=seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _make_downtrend_overhead_series(*, seed: int = 17) -> pd.DataFrame:
    """Base then a long decline flips the EMA50 slope negative, then recovery.

    Price crosses the pivot but the 50d EMA slope is negative (EC-06).
    """
    base = _make_bo_series(seed=seed, breakout_bars=0)
    closes = list(base["close"].values)
    volumes = list(base["volume"].values)
    bc = closes[-1]
    decline = [bc * (1.0 - 0.006 * i) for i in range(1, 26)]  # -15% over 25 bars
    recovery = [decline[-1] * (1.0 + 0.03), decline[-1] * (1.0 + 0.06), bc * 1.04]
    closes += decline + recovery
    volumes += [900_000] * 25 + [2_800_000] * 3
    n = len(closes)
    ranges = np.full(n, 0.06)
    opens, highs, lows = _bars_from_closes(np.asarray(closes), ranges, np.asarray(volumes), seed=seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


# Scenario aliases used by the mini-universe screen test.
def make_scenario(kind: str) -> pd.DataFrame:
    builders = {
        "textbook_classic": lambda: _make_bo_series(breakout_surge=3.5),
        "classic_strong": lambda: _make_bo_series(breakout_surge=2.2),
        "lower_base": _make_lower_base_series,
        "near_miss": lambda: _make_bo_series(breakout_surge=1.2),
        "no_dryup": lambda: _make_bo_series(volume_dryup=0.8, breakout_surge=3.0),
        "no_base": _make_no_base_series,
        "extended": lambda: _make_bo_series(surfing_dist=16.0),
        "garbage": _make_garbage_series,
        "stale_base": lambda: _make_bo_series(base_duration=60, decay=False, breakout_surge=3.0),
        "low_impulse": lambda: _make_bo_series(impulse_pct=15.0),
        "high_adr": lambda: _make_bo_series(adr_pct=14.0),
        "vshape": _make_vshape_series,
        "downtrend": _make_downtrend_overhead_series,
    }
    return builders[kind]()
