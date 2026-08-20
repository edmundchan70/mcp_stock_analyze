"""Deterministic synthetic OHLCV scenario builders for EP setup tests.

Every series is a phase sequence (quiet → event shock → pullback →
recovery / base) so feature booleans are reproducible. No random walks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def bars_from_closes(closes, volumes, ranges=None, seed: int = 7) -> pd.DataFrame:
    """Build OHLC bars from closes + volume; 1% half-range wiggles."""
    closes = np.asarray(closes, dtype=float)
    volumes = np.asarray(volumes, dtype=float)
    n = len(closes)
    if ranges is None:
        ranges = np.full(n, 0.02)
    ranges = np.asarray(ranges, dtype=float)
    rng = np.random.default_rng(seed)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    for i in range(n):
        c = closes[i]
        half = c * ranges[i] / 2.0
        highs[i] = c + half
        lows[i] = c - half
        opens[i] = lows[i] + (highs[i] - lows[i]) * rng.uniform(0.3, 0.7)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def make_ep_textbook(
    *,
    n_quiet: int = 50,
    quiet: float = 100.0,
    event_close: float = 112.0,
    event_vol: float = 4_000_000,
    post_high: float = 116.0,
    post_vol: float = 1_600_000,
    pullback_low: float = 98.0,
    pullback_vol: float = 500_000,
    recovery_top: float = 115.0,
    recovery_vol: float = 1_200_000,
    n_pull: int = 10,
    n_recover: int = 10,
    n_top: int = 4,
    top_vol: float = 1_000_000,
    quiet_vol: float = 1_000_000,
) -> pd.DataFrame:
    """Textbook EP: quiet → 4x event gap-up → pivot high → low-volume
    pullback → higher-volume recovery up-leg → tight top.

    With defaults every feature should hold: volume_spike (4x), pullback
    contrast (~15% depth on ≤0.5x event volume), a 5-40d base, an aligned
    EMA stack with touched-and-held EMAs, and event-anchored VWAP support.
    """
    closes: list[float] = [quiet] * n_quiet
    volumes: list[float] = [quiet_vol] * n_quiet

    closes.append(event_close)          # event day (gap shock)
    volumes.append(event_vol)
    closes.append(post_high)            # pivot high (base highest high)
    volumes.append(post_vol)
    closes += list(np.linspace(post_high, pullback_low, n_pull))  # pullback
    volumes += [pullback_vol] * n_pull
    closes += list(np.linspace(pullback_low, recovery_top, n_recover))  # up-leg
    volumes += [recovery_vol] * n_recover
    closes += [recovery_top] * n_top    # tight top
    volumes += [top_vol] * n_top
    return bars_from_closes(closes, volumes)


def make_no_base_series(n: int = 130, *, seed: int = 3) -> pd.DataFrame:
    """Monotonic rise with constant volume — no pivot-in-the-middle base."""
    closes = np.linspace(100.0, 170.0, n)
    volumes = np.full(n, 1_500_000.0)
    return bars_from_closes(closes, volumes, seed=seed)


def make_no_pullback_series(*, n_quiet: int = 50) -> pd.DataFrame:
    """Event gap-up then flat at the event level — no >=10% pullback."""
    closes = [100.0] * n_quiet + [112.0, 113.0, 112.5, 113.0, 112.0, 113.5, 112.5]
    volumes = [1_000_000] * n_quiet + [4_000_000, 1_000_000] + [1_000_000] * 5
    return bars_from_closes(closes, volumes)


def make_mild_spike_series(*, n_quiet: int = 50) -> pd.DataFrame:
    """Event volume only 1.5x the 50d average — volume_spike must fail."""
    closes = [100.0] * n_quiet + [112.0, 116.0]
    closes += list(np.linspace(116.0, 98.0, 10))
    closes += list(np.linspace(98.0, 115.0, 10))
    closes += [115.0] * 4
    volumes = [1_000_000] * n_quiet + [1_500_000, 1_200_000]
    volumes += [500_000] * 10 + [1_200_000] * 10 + [1_000_000] * 4
    return bars_from_closes(closes, volumes)


def make_vwap_fallback_series(*, n_quiet: int = 50) -> pd.DataFrame:
    """Event-anchored VWAP too low to be touched; the pivot anchor holds.

    Quiet at 100 → huge-volume event (close ~102, 8M) → gap to the pivot
    high (122) → shallow pullback (~115.5 low) → recovery to 120. Price
    stays well above the event VWAP (~110.7) but dips within 1.5% of the
    pivot-anchored VWAP (~118.4) → vwap_anchor must fall back to "pivot".
    """
    closes = [100.0] * n_quiet
    volumes = [1_000_000] * n_quiet
    closes += [102.0]                      # event (massive volume, near-flat)
    volumes += [8_000_000]
    closes += [120.0]                      # pivot high (post-event higher high)
    volumes += [1_500_000]
    closes += list(np.linspace(120.0, 117.0, 5))   # shallow pullback
    volumes += [500_000] * 5
    closes += list(np.linspace(117.0, 120.0, 5))   # recovery to pivot zone
    volumes += [1_200_000] * 5
    return bars_from_closes(closes, volumes)


def make_short_series(n: int = 40, *, seed: int = 5) -> pd.DataFrame:
    """Too few bars (< MIN_BARS) — score_ep_setup must return all-False."""
    closes = np.linspace(100.0, 120.0, n)
    volumes = np.full(n, 1_000_000.0)
    return bars_from_closes(closes, volumes, seed=seed)
