"""Premarket grep pure-math metrics — strength tier + volume flag."""

from __future__ import annotations

from typing import Optional


def strength_tier(change_pct: float) -> int:
    """Deterministic tier from premarket change % vs prior close."""
    if change_pct >= 10.0:
        return 5
    if change_pct >= 7.5:
        return 4
    if change_pct >= 5.0:
        return 3
    return 2


def volume_flag(volume: Optional[float], adv_20d: Optional[float], min_mult: float) -> bool:
    """True when today's volume >= min_mult × 20d ADV (flag off when min_mult = 0)."""
    if not min_mult or not volume or not adv_20d:
        return False
    return float(volume) >= float(min_mult) * float(adv_20d)


__all__ = ["strength_tier", "volume_flag"]
