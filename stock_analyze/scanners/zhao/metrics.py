"""照妖鏡 (zhao) pure-math metrics — SMA20, RS vs benchmark, 52w proximity, strength tiers.

All functions are stateless over close/high arrays (DataFrame ``.close``
Series or plain sequences). Percentages are percentage points (e.g. 4.2 = 4.2%).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def sma20(closes: Sequence[float]) -> float:
    """Trailing 20-bar simple moving average of the close series."""
    arr = np.asarray(closes, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(arr[-20:].mean())


def pct_change(a: float, b: float) -> float:
    """(a / b - 1) * 100; 0.0 when the base is missing."""
    if not b:
        return 0.0
    return (float(a) / float(b) - 1.0) * 100.0


def rel_strength_20d(stock_closes: Sequence[float], bench_closes: Sequence[float]) -> float:
    """20d relative strength vs benchmark in percentage points.

    ``(stock_20d_return% - bench_20d_return%)`` using close[-1] vs close[-21].
    Returns 0.0 when either series has fewer than 21 bars.
    """
    s = np.asarray(stock_closes, dtype=float)
    b = np.asarray(bench_closes, dtype=float)
    if s.size < 21 or b.size < 21:
        return 0.0
    s_ret = (s[-1] / s[-21] - 1.0) * 100.0
    b_ret = (b[-1] / b[-21] - 1.0) * 100.0
    return float(s_ret - b_ret)


def pct_from_high(close: float, high_252: float) -> float:
    """(close / 252d high - 1) * 100 — negative below the high, 0 at the high."""
    if not high_252:
        return 0.0
    return (float(close) / float(high_252) - 1.0) * 100.0


def strength_tier_realtime(margin_pct: float) -> int:
    """Realtime tier from stock-minus-benchmark margin %."""
    if margin_pct >= 3.0:
        return 5
    if margin_pct >= 1.5:
        return 4
    if margin_pct > 0.0:
        return 3
    return 2


def strength_tier_daily(rs_pct: float, pct_from_high: float) -> int:
    """Daily tier from 20d RS % + 52-week-high proximity %."""
    if rs_pct >= 10.0 and pct_from_high >= -5.0:
        return 5
    if rs_pct >= 5.0 and pct_from_high >= -10.0:
        return 4
    if rs_pct >= 0.0 and pct_from_high >= -15.0:
        return 3
    return 2


__all__ = [
    "pct_change",
    "pct_from_high",
    "rel_strength_20d",
    "sma20",
    "strength_tier_daily",
    "strength_tier_realtime",
]
