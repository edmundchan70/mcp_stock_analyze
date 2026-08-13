"""BO Watchlist Funnel Gatekeeper — ADV / EMA10 / Dry-up gates + Q_base scoring.

Pure-math gate-only functions that consume BoSetupRating objects (with
the extra OHLCV-derived fields computed in runner.py) to produce a funnel
survivor list.  The structural ``rating`` from ``score_bo_setup()`` is
kept as a reference field; the funnel ``funnel_stars`` (from Q_base) is
the *replacement* gate for Agent 2 enrichment.

Port of ``spike_watchlist.py``, adapted to operate on in-memory ratings
rather than re-fetched OHLCV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

# ── Profile definitions ──────────────────────────────────────────────

WATCHLIST_PROFILES = {
    "best":           {"adv": 50_000_000, "ema": 5.0, "dryup": 0.0,  "base": 40},
    "moderate-lose":  {"adv": 50_000_000, "ema": 8.0, "dryup": 0.0,  "base": 40},
    "widen":          {"adv": 30_000_000, "ema": 8.0, "dryup": 0.0,  "base": 40},
}

# ── Gate functions (pure math — no side effects) ─────────────────────


def g2_adv_dollar(adv_20d: float, floor: float) -> bool:
    """G2: 20-day average dollar volume >= *floor*.

    ``adv_20d`` is computed once in runner.py from OHLCV and persisted
    on ``BoSetupRating``.  This gate is a pure predicate over that value.
    """
    return adv_20d >= floor


def g3_ema10_proximity(ema10_dist_pct: float, ema10_rising: bool, max_pct: float) -> bool:
    """G3: |close - EMA10| <= *max_pct* AND EMA10 is rising."""
    return ema10_dist_pct <= max_pct and ema10_rising


def g4_base_duration(duration_days: int, base_max: int) -> bool:
    """G4: base_duration is truthy AND 5 <= days <= base_max."""
    return 5 <= duration_days <= base_max


def g5_volume_dryup(dryup_vol_ratio: float, max_ratio: Optional[float]) -> bool:
    """G5: dry-up ratio <= max_ratio, or always-pass when disabled."""
    if max_ratio is None:
        return True
    return dryup_vol_ratio <= max_ratio


# ── Q_base scoring ───────────────────────────────────────────────────


def q_base_to_stars(score: int) -> int:
    """Map Q_base composite score to funnel star tier (5/4/3/0)."""
    if score >= 90:
        return 5
    if score >= 75:
        return 4
    if score >= 60:
        return 3
    return 0


def compute_q_base(
    vci: float,
    hl: int,
    tightness: float,
    prior_pct: float,
    dryup: float,
    surfing: float,
) -> int:
    """Composite Q_base score (max 100).

    Scoring rubric ported from ``spike_watchlist.py``:
    - VCI   ≤0.50→30  ≤0.60→25  ≤0.65→15
    - HL    ≥3→20     ≥2→15    ≥1→10
    - Tightness  ≤0.60→20  ≤0.75→15  ≤1.00→8
    - Prior %    ≥60→15   ≥40→12   ≥30→10
    - Dry-up    ≤0.30→10  ≤0.40→8   ≤0.50→6
    - |Surfing|  ≤1.5→5   ≤2.5→3   ≤3.5→1
    """
    score = 0
    if vci <= 0.50:
        score += 30
    elif vci <= 0.60:
        score += 25
    elif vci <= 0.65:
        score += 15

    if hl >= 3:
        score += 20
    elif hl == 2:
        score += 15
    elif hl == 1:
        score += 10

    if tightness <= 0.60:
        score += 20
    elif tightness <= 0.75:
        score += 15
    elif tightness <= 1.00:
        score += 8

    if prior_pct >= 60:
        score += 15
    elif prior_pct >= 40:
        score += 12
    elif prior_pct >= 30:
        score += 10

    if dryup <= 0.30:
        score += 10
    elif dryup <= 0.40:
        score += 8
    elif dryup <= 0.50:
        score += 6

    ad = abs(surfing)
    if ad <= 1.5:
        score += 5
    elif ad <= 2.5:
        score += 3
    elif ad <= 3.5:
        score += 1

    return score


# ── Funnel gate ──────────────────────────────────────────────────────


@dataclass
class FunnelResult:
    """Output of a single funnel gate run."""

    survivors: list[dict[str, Any]] = field(default_factory=list)
    gate: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "passed": {"g1_impulse": 0, "g2_adv": 0, "g3_ema10": 0, "g4_base": 0, "g5_dryup": 0},
            "failed": {"g1_impulse": 0, "g2_adv": 0, "g3_ema10": 0, "g4_base": 0, "g5_dryup": 0},
        },
    )


def apply_funnel(
    ratings: list[Any],
    profile: str,
) -> FunnelResult:
    """Run the 5-gate funnel on a list of ``BoSetupRating``-compatible objects.

    Args:
        ratings: List of BoSetupRating objects (or dicts with the same keys).
        profile: One of ``"best"``, ``"moderate-lose"``, ``"widen"``.

    Returns:
        FunnelResult with survivors, gate breakdown, and tradable count.
    """
    cfg = WATCHLIST_PROFILES[profile]
    adv_floor = cfg["adv"]
    ema_max = cfg["ema"]
    dryup_max = cfg["dryup"] if cfg["dryup"] > 0 else None
    base_max = cfg["base"]

    result = FunnelResult()
    for r in ratings:
        if isinstance(r, dict):
            sym = r.get("symbol", "?")
            prior_impulse = r.get("prior_impulse", False)
            adv_20d = r.get("adv_20d", 0.0)
            ema10_dist_pct = r.get("ema10_dist_pct", 999.0)
            ema10_rising = r.get("ema10_rising", False)
            base_duration = r.get("base_duration", False)
            base_duration_days = r.get("base_duration_days", 0)
            dryup_vol_ratio = r.get("dryup_vol_ratio", 999.0)
            prior_impulse_pct = r.get("prior_impulse_pct", 0.0)
            vci_ratio = r.get("vci_ratio", 0.65)
            higher_lows_count = r.get("higher_lows_count", 0)
            surfing_dist_pct = r.get("surfing_dist_pct", 0.0)
            adr20_pct = r.get("adr20_pct", 0.0)
            tightness = r.get("tightness", 999.0)
        else:
            sym = getattr(r, "symbol", "?")
            prior_impulse = getattr(r, "prior_impulse", False)
            adv_20d = getattr(r, "adv_20d", 0.0)
            ema10_dist_pct = getattr(r, "ema10_dist_pct", 999.0)
            ema10_rising = getattr(r, "ema10_rising", False)
            base_duration = getattr(r, "base_duration", False)
            base_duration_days = getattr(r, "base_duration_days", 0)
            dryup_vol_ratio = getattr(r, "dryup_vol_ratio", 999.0)
            prior_impulse_pct = getattr(r, "prior_impulse_pct", 0.0)
            vci_ratio = getattr(r, "vci_ratio", 0.65)
            higher_lows_count = getattr(r, "higher_lows_count", 0)
            surfing_dist_pct = getattr(r, "surfing_dist_pct", 0.0)
            adr20_pct = getattr(r, "adr20_pct", 0.0)
            tightness = getattr(r, "tightness", 999.0)

        # G1 — prior impulse
        g1_ok = bool(prior_impulse)
        result.gate["passed" if g1_ok else "failed"]["g1_impulse"] += 1

        # G2 — ADV dollar liquidity
        g2_ok = g2_adv_dollar(adv_20d, adv_floor)
        result.gate["passed" if g2_ok else "failed"]["g2_adv"] += 1

        # G3 — EMA10 proximity + rising
        g3_ok = g3_ema10_proximity(ema10_dist_pct, ema10_rising, ema_max)
        result.gate["passed" if g3_ok else "failed"]["g3_ema10"] += 1

        # G4 — base duration
        g4_ok = bool(base_duration) and g4_base_duration(base_duration_days, base_max)
        result.gate["passed" if g4_ok else "failed"]["g4_base"] += 1

        # G5 — volume dry-up (scoring-only in all profiles)
        g5_ok = g5_volume_dryup(dryup_vol_ratio, dryup_max)
        result.gate["passed" if g5_ok else "failed"]["g5_dryup"] += 1

        if not (g1_ok and g2_ok and g3_ok and g4_ok and g5_ok):
            continue

        qb = compute_q_base(vci_ratio, higher_lows_count, tightness, prior_impulse_pct, dryup_vol_ratio, surfing_dist_pct)
        stars = q_base_to_stars(qb)

        if stars < 3:
            continue

        result.survivors.append({
            "symbol": sym,
            "stars": stars,
            "q_base": qb,
            "prior_impulse_pct": round(prior_impulse_pct, 1),
            "adv_20d": round(adv_20d, 0),
            "ema10_dist_pct": round(ema10_dist_pct, 2),
            "base_duration": base_duration_days,
            "dryup_vol_ratio": round(dryup_vol_ratio, 3),
            "vci": round(vci_ratio, 4),
            "higher_lows": higher_lows_count,
            "tightness": round(tightness, 3),
        })

    return result


def tradable_count(survivors: list[dict[str, Any]]) -> int:
    """Count survivors at or above the 3★ floor (Q_base >= 60)."""
    return sum(1 for c in survivors if c.get("stars", 0) >= 3)


__all__ = [
    "FunnelResult",
    "WATCHLIST_PROFILES",
    "apply_funnel",
    "compute_q_base",
    "g2_adv_dollar",
    "g3_ema10_proximity",
    "g4_base_duration",
    "g5_volume_dryup",
    "q_base_to_stars",
    "tradable_count",
]
