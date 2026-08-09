"""VCP pattern detection — pure math from OHLCV DataFrames.

All scoring rules follow the VCP Structural Rating Rubric in glossary.md.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional, Tuple

import numpy as np
import pandas as pd

from stock_analyze.models.vcp import VcpContraction, VcpStructuralRating

logger = logging.getLogger(__name__)

# ── RS Line ──────────────────────────────────────────────────────────


def compute_rs_line(stock_df: pd.DataFrame, spy_df: pd.DataFrame) -> pd.Series:
    """Compute Relative Strength line: stock_close / spy_close."""
    aligned_stock = stock_df["close"].copy()
    aligned_spy = spy_df["close"].copy()
    common = aligned_stock.index.intersection(aligned_spy.index)
    if len(common) < 10:
        return pd.Series(dtype=float)
    return aligned_stock.loc[common] / aligned_spy.loc[common]


def compute_rs_rating(rs_line: pd.Series) -> float:
    """Compute RS rating (0-100) from a relative strength line.

    Mirrors IBD style: compare current RS value to its N-day range.
    Returns percentile rank (0-100).
    """
    if len(rs_line) < 5:
        return 50.0
    current = rs_line.iloc[-1]
    lo = rs_line.rolling(window=252).min().iloc[-1] if len(rs_line) >= 252 else rs_line.min()
    hi = rs_line.rolling(window=252).max().iloc[-1] if len(rs_line) >= 252 else rs_line.max()
    rng = hi - lo
    if rng == 0:
        return 50.0
    return ((current - lo) / rng) * 100.0


# ── Stage 2 Trend Template ───────────────────────────────────────────


def check_stage2_trend(df: pd.DataFrame, rs_rating: float) -> Tuple[bool, dict[str, Any]]:
    """Check Minervini's Stage 2 trend template.

    Returns (is_stage2, meta dict with sma values, 52W-high proxy, etc.)
    """
    if len(df) < 200:
        return False, {"error": "insufficient_bars"}

    close = df["close"]

    sma50 = close.rolling(window=50).mean().iloc[-1]
    sma150 = close.rolling(window=150).mean().iloc[-1] if len(df) >= 150 else None
    sma200 = close.rolling(window=200).mean().iloc[-1]
    current_price = close.iloc[-1]
    high_52w = close.rolling(window=252).max().iloc[-1] if len(df) >= 252 else close.max()
    sma200_prev = close.rolling(window=200).mean().iloc[-2]

    rising_200 = sma200 > sma200_prev

    # Check alignment
    if sma150 is not None:
        price_above_smas = current_price > sma50 > sma150 > sma200
    else:
        price_above_smas = current_price > sma50 > sma200

    price_above_200 = current_price > sma200
    proximity_52w = (current_price / high_52w) * 100.0 if high_52w > 0 else 0.0

    is_stage2 = bool(price_above_smas and rising_200 and rs_rating >= 70.0)

    meta = {
        "current_price": current_price,
        "sma50": sma50,
        "sma150": sma150,
        "sma200": sma200,
        "high_52w": high_52w,
        "proximity_52w_pct": proximity_52w,
        "price_above_smas": bool(price_above_smas),
        "price_above_200": bool(price_above_200),
        "rising_200_sma": bool(rising_200),
        "rs_rating": rs_rating,
    }
    return is_stage2, meta


# ── Swing Points ────────────────────────────────────────────────────


def find_vcp_swing_points(df: pd.DataFrame, window: int = 10) -> Tuple[list[Tuple[int, float, str]], Any]:
    """Find swing highs and lows using rolling max/min pivots.

    Args:
        df: DataFrame with 'high' and 'low' columns.
        window: Number of bars each side for pivot detection (default 10).

    Returns:
        Tuple of (swings: list of (index, price, 'H'/'L'), df) where swings
        are sorted by index ascending.
    """
    if len(df) < window * 2:
        return [], df

    high_col = df["high"].values
    low_col = df["low"].values
    n = len(df)

    swings: list[Tuple[int, float, str]] = []

    # Find pivot highs: a bar whose high is higher than window bars on each side
    for i in range(window, n - window):
        if high_col[i] == np.max(high_col[i - window : i + window + 1]):
            swings.append((i, high_col[i], "H"))

    # Find pivot lows: a bar whose low is lower than window bars on each side
    for i in range(window, n - window):
        if low_col[i] == np.min(low_col[i - window : i + window + 1]):
            swings.append((i, low_col[i], "L"))

    # Sort by index
    swings.sort(key=lambda x: x[0])

    # Deduplicate adjacent same-type swings (take the more extreme one)
    filtered: list[Tuple[int, float, str]] = []
    for s in swings:
        if filtered and filtered[-1][2] == s[2]:
            prev = filtered.pop()
            if s[2] == "H":
                filtered.append((s[0], max(prev[1], s[1]), "H"))
            else:
                filtered.append((s[0], min(prev[1], s[1]), "L"))
        else:
            filtered.append(s)

    return filtered, df


def _swing_to_contraction_pairs(
    swings: list[Tuple[int, float, str]],
) -> list[Tuple[Tuple[int, float, str], Tuple[int, float, str]]]:
    """Convert alternating swing list to (high, low) contraction pairs.

    Only keeps pairs where high comes before low (descending from peak to trough).
    """
    pairs: list[Tuple[Tuple[int, float, str], Tuple[int, float, str]]] = []
    for i in range(len(swings) - 1):
        curr = swings[i]
        nxt = swings[i + 1]
        if curr[2] == "H" and nxt[2] == "L" and nxt[0] > curr[0]:
            pairs.append((curr, nxt))
    return pairs


# ── Contraction Detection ───────────────────────────────────────────


def detect_contractions(
    df: pd.DataFrame,
    swings: list[Tuple[int, float, str]],
) -> list[VcpContraction]:
    """Detect VCP contractions from swing point pairs.

    Returns list of VcpContraction oldest first (by pivot index).
    """
    pairs = _swing_to_contraction_pairs(swings)
    if not pairs:
        return []

    volume = df["volume"].values
    contractions: list[VcpContraction] = []

    for idx, (high_swing, low_swing) in enumerate(pairs):
        hi_idx, hi_price, _ = high_swing
        lo_idx, lo_price, _ = low_swing

        dollar_range = hi_price - lo_price
        depth_pct = (dollar_range / hi_price) * 100.0 if hi_price > 0 else 0.0
        duration = lo_idx - hi_idx
        if duration < 1:
            duration = 1

        # Average volume within contraction window
        seg_vol = volume[hi_idx : lo_idx + 1]
        avg_vol = float(np.mean(seg_vol)) if len(seg_vol) > 0 else 0.0

        contractions.append(
            VcpContraction(
                index=idx,
                high_pivot=float(hi_price),
                low_pivot=float(lo_price),
                dollar_range=float(dollar_range),
                depth_pct=float(depth_pct),
                avg_volume=float(avg_vol),
                duration_days=int(duration),
            )
        )

    return contractions


# ── Tight Closes ──────────────────────────────────────────────────


def check_tight_closes(
    df: pd.DataFrame,
    n_days: int = 4,
) -> Tuple[bool, float, float]:
    """Check for tight closes signature at the end of a contraction.

    Returns (found, span_pct, cv_pct).
    """
    if len(df) < n_days:
        return False, 0.0, 0.0

    last_n = df.iloc[-n_days:]
    daily_ranges = ((last_n["high"] - last_n["low"]) / last_n["close"]) * 100.0

    span = daily_ranges.max() - daily_ranges.min()
    mean_range = daily_ranges.mean()
    cv = (daily_ranges.std() / mean_range) * 100.0 if mean_range > 0 else 999.0

    return True, float(span), float(cv)


# ── Scoring Functions ───────────────────────────────────────────────


def score_stage2_and_proximity(meta: dict[str, Any]) -> int:
    """Score Stage 2 trend + 52W-high proximity.

    Returns 5, 4, or 3.
    """
    is_stage2 = bool(meta.get("price_above_smas", False))
    rising_200 = bool(meta.get("rising_200_sma", False))
    rs = float(meta.get("rs_rating", 0))
    prox = float(meta.get("proximity_52w_pct", 0))

    if not is_stage2 or not rising_200:
        return 3

    if rs >= 85.0 and prox >= 90.0:
        return 5
    elif rs >= 70.0 and prox >= 80.0:
        return 4
    else:
        return 3


def score_contraction_count(contractions: list[VcpContraction]) -> int:
    """Score based on number of detected VCP waves."""
    k = len(contractions)
    if 3 <= k <= 4:
        return 5
    if k == 2 or k == 5:
        return 4
    return 3


def score_trough_symmetry(contractions: list[VcpContraction]) -> int:
    """Score trough (low pivot) symmetry — lows must be strictly higher.

    Returns 5, 4, or 3.
    """
    if len(contractions) < 2:
        return 3

    lows = [c.low_pivot for c in contractions]
    all_higher = True
    strictly_higher = True

    for i in range(1, len(lows)):
        if lows[i] <= lows[i - 1]:
            strictly_higher = False
            all_higher = False
            break
        if lows[i] < lows[i - 1] * 1.001:  # Not strictly higher by meaningful amount
            strictly_higher = False

    if all_higher and strictly_higher:
        return 5
    elif all_higher:
        return 4
    return 3


def score_peak_symmetry(contractions: list[VcpContraction]) -> int:
    """Score peak (high pivot) symmetry — highs should be flat or rising.

    Returns 5, 4, or 3.
    """
    if len(contractions) < 2:
        return 3

    highs = [c.high_pivot for c in contractions]
    score = 5

    for i in range(1, len(highs)):
        ratio = highs[i] / highs[i - 1] if highs[i - 1] > 0 else 1.0
        if ratio < 0.95:
            return 3  # Descending triangle
        if ratio < 0.99 and score == 5:
            score = 4  # Minor slope

    return score


def score_dollar_range(contractions: list[VcpContraction]) -> int:
    """Score dollar range contraction — ranges should shrink monotonically.

    Returns 5, 4, or 3.
    """
    if len(contractions) < 2:
        return 3

    ranges = [c.dollar_range for c in contractions]
    score = 5

    for i in range(1, len(ranges)):
        if ranges[i] > ranges[i - 1]:
            return 3  # Expanding
        ratio = ranges[i] / ranges[i - 1] if ranges[i - 1] > 0 else 1.0
        if ratio > 0.75 and score == 5:
            score = 4  # Not monotonic enough

    return score


def score_depth(contractions: list[VcpContraction]) -> int:
    """Score depth percentage monotonicity — depths should shrink.

    Returns 5, 4, or 3.
    """
    if len(contractions) < 2:
        return 3

    depths = [c.depth_pct for c in contractions]
    score = 5

    for i in range(1, len(depths)):
        if depths[i] >= depths[i - 1]:
            return 3  # Expanding depth
        ratio = depths[i] / depths[i - 1] if depths[i - 1] > 0 else 1.0
        if ratio > 0.75 and score == 5:
            score = 4

    return score


def score_tight_closes(span_pct: float, cv_pct: float, found: bool) -> int:
    """Score tight closes signature.

    Returns 5, 4, or 3.
    """
    if not found:
        return 3

    if span_pct <= 1.25 and cv_pct <= 0.8:
        return 5
    elif span_pct <= 2.0 and cv_pct <= 1.5:
        return 4
    return 3


def score_volume_decay(contractions: list[VcpContraction], df: pd.DataFrame) -> int:
    """Score volume decay rate across contractions.

    Returns 5, 4, or 3.
    """
    if len(contractions) < 2:
        return 3

    volumes = [c.avg_volume for c in contractions]
    score = 5

    for i in range(1, len(volumes)):
        if volumes[i] >= volumes[i - 1]:
            return 3  # Expanding volume
        drop_pct = (volumes[i - 1] - volumes[i]) / volumes[i - 1] * 100.0 if volumes[i - 1] > 0 else 0
        if drop_pct < 15.0 and score == 5:
            score = 4  # Not strong enough decay

    # Check pivot volume: last contraction's avg volume vs SMA20
    if len(df) >= 20:
        volume_sma20 = df["volume"].rolling(window=20).mean().iloc[-1]
        last_vol = contractions[-1].avg_volume
        if volume_sma20 > 0 and last_vol > volume_sma20:
            return 3  # Pivot volume too high

    return score


def score_time_contraction(contractions: list[VcpContraction]) -> int:
    """Score time contraction — each wave should take similar or less time.

    Returns 5, 4, or 3.
    """
    if len(contractions) < 2:
        return 3

    durations = [c.duration_days for c in contractions]
    strictly_contracting = True
    bounded = True

    for i in range(1, len(durations)):
        if durations[i] >= durations[i - 1]:
            strictly_contracting = False
        if durations[i] > durations[i - 1] * 1.2:
            bounded = False

    # Check "eternal base"
    if durations[-1] > durations[0] * 3:
        return 3

    if strictly_contracting:
        return 5
    elif bounded:
        return 4
    return 3


# ── Main Scoring ────────────────────────────────────────────────────


def score_vcp(
    df: pd.DataFrame,
    spy_df: pd.DataFrame,
    *,
    symbol: str = "",
    exchange: str = "",
    as_of: Optional[date] = None,
) -> Optional[VcpStructuralRating]:
    """Score a stock for VCP using pure math from OHLCV.

    Returns VcpStructuralRating or None if insufficient data.
    """
    if df is None or len(df) < 200:
        return None
    if spy_df is None or len(spy_df) < 50:
        return None

    day = as_of or date.today()

    # 1. Compute RS line
    rs_line = compute_rs_line(df, spy_df)
    if len(rs_line) < 5:
        return None
    rs_rating = compute_rs_rating(rs_line)

    # 2. Check Stage 2
    is_stage2, meta = check_stage2_trend(df, rs_rating)

    # 3. Find swing points
    swings, _ = find_vcp_swing_points(df, window=10)

    # 4. Detect contractions
    contractions = detect_contractions(df, swings)

    # 5. Check tight closes
    tc_found, tc_span, tc_cv = check_tight_closes(df, n_days=4)

    # 6. Score each parameter
    s_stage2 = score_stage2_and_proximity(meta)
    s_count = score_contraction_count(contractions)
    s_trough = score_trough_symmetry(contractions)
    s_peak = score_peak_symmetry(contractions)
    s_range = score_dollar_range(contractions)
    s_depth = score_depth(contractions)
    s_tight = score_tight_closes(tc_span, tc_cv, tc_found)
    s_volume = score_volume_decay(contractions, df)
    s_time = score_time_contraction(contractions)

    scores = [s_stage2, s_count, s_trough, s_peak, s_range, s_depth, s_tight, s_volume, s_time]

    # Aggregate: take the mode (most common score) but weighted by severity
    # If any score is 3, the best we can get is 4 (and only if majority are 4-5)
    has_3 = 3 in scores
    count_5 = scores.count(5)
    count_4 = scores.count(4)

    if has_3:
        # Need at least 5 params at 4+ to get 4★
        if count_5 + count_4 >= 5:
            structural_rating = 4
        else:
            structural_rating = 3
    elif count_5 >= 6:
        structural_rating = 5
    elif count_5 >= 3 or count_4 >= 5:
        structural_rating = 4
    else:
        structural_rating = 4  # Fallback: mostly 4★ territory

    # Edge: no Stage 2 → max 3
    if not is_stage2:
        structural_rating = min(structural_rating, 3)

    # Edge: no contractions or only 1
    if len(contractions) < 2:
        structural_rating = min(structural_rating, 3)

    from stock_analyze.models.vcp import STRUCTURAL_LABELS

    label = STRUCTURAL_LABELS.get(structural_rating, "sub_standard")

    return VcpStructuralRating(
        symbol=symbol,
        exchange=exchange,
        structural_rating=structural_rating,  # type: ignore[arg-type]
        structural_label=label,  # type: ignore[arg-type]
        stage2_trend=is_stage2,
        rs_rating=rs_rating,
        proximity_52w_pct=float(meta.get("proximity_52w_pct", 0)),
        contraction_count=len(contractions),
        trough_symmetry_score=s_trough,
        peak_symmetry_score=s_peak,
        dollar_range_score=s_range,
        depth_score=s_depth,
        tight_closes_score=s_tight,
        volume_decay_score=s_volume,
        time_contraction_score=s_time,
        contractions=contractions,
        as_of=day,
    )
