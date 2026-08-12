"""Qullamaggie BO (breakout) setup detection — pure math from OHLCV.

Rules follow the research formalization in
`Qullamaggie Breakout Quantitative Test Suite.txt`:
- Prior impulse >= 30% over a 20-63 day window (Stage 2).
- ADR20 within [4%, 12%] envelope (Stage 1).
- Base 10-40 trading days, VCI (ATR5/ATR20) <= 0.65, narrow 3-day range (Stage 3).
- KDE pivot (Gaussian, bandwidth = 3% of price) in the base upper quartile.
- Higher lows (S_HL >= 1) into the pivot.
- Breakout: close > pivot + volume surge >= 1.5x (Stage 4).
- Surfing: close within 8% of EMA10; > 8% above = overextended clamp to 3★.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from stock_analyze.models.bo import BO_LABELS, BoBase, BoNearMiss, BoScanBucket, BoSetupRating
from stock_analyze.scanners.bo.gates import passes_adr_envelope
from stock_analyze.scanners.vcp.metrics import compute_rs_line, compute_rs_rating

logger = logging.getLogger(__name__)

MIN_IMPULSE_PCT = 30.0
ADR_LO, ADR_HI = 4.0, 12.0
BASE_MIN_DAYS, BASE_MAX_DAYS = 5, 40
VCI_MAX = 0.65
SURFING_MAX_PCT = 8.0
SURGE_MIN = 1.5
DRYUP_MAX = 0.5
SURGE_STRONG = 2.0
SURGE_TEXTBOOK = 3.0
MIN_BARS = 90

# Canonical ordering of the 9 essential boolean parameters persisted on
# BoSetupRating.  ``derive_near_miss`` uses this list to build
# ``passed_essentials`` / ``failed_essentials`` arrays.
ESSENTIAL_KEYS = [
    "prior_impulse", "adr20", "base_duration", "vci", "ma_stack",
    "pivot_kde", "higher_lows", "dryup", "volume_surge",
]


# ── Stage 2: prior impulse ───────────────────────────────────────────


def prior_impulse(closes, window: tuple[int, int] = (20, 63)) -> float:
    """Maximum percentage gain over a rolling 20-63 day window.

    For every end bar ``e``, the low must sit between 20 and 63 bars before
    ``e``; the gain from that low to ``close[e]`` is measured. Returns the
    maximum over the whole series (%).
    """
    closes = np.asarray(closes, dtype=float)
    lo_w, hi_w = window
    n = len(closes)
    if n < hi_w + 1:
        return 0.0
    best = 0.0
    for e in range(hi_w, n):
        seg = closes[e - hi_w : e - lo_w + 1]
        if len(seg) == 0:
            continue
        m = seg.min()
        if m > 0:
            best = max(best, (closes[e] / m - 1.0) * 100.0)
    return float(best)


# ── Stage 1: ADR20 envelope ──────────────────────────────────────────


def avg_daily_range_pct(df: pd.DataFrame, window: int = 20) -> float:
    """20-day Average Daily Range % = mean((high - low) / close)."""
    if df is None or len(df) < window:
        return 0.0
    ranges = ((df["high"] - df["low"]) / df["close"]) * 100.0
    return float(ranges.tail(window).mean())


# ── Stage 3: volatility contraction index ────────────────────────────


def _atr(df: pd.DataFrame, window: int) -> float:
    close = df["close"]
    prev_close = close.shift(1).fillna(close)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(window).mean().iloc[-1])


def vci_atr(df: pd.DataFrame, short: int = 5, medium: int = 20) -> float:
    """Volatility Contraction Index = ATR_short / ATR_medium (last bar)."""
    if df is None or len(df) < medium:
        return 999.0
    atr_s = _atr(df, short)
    atr_m = _atr(df, medium)
    return float(atr_s / atr_m) if atr_m > 0 else 999.0


def _narrow_three_day(df: pd.DataFrame) -> bool:
    """Pre-breakout 3-day range must be tight relative to ADR20."""
    if len(df) < 4:
        return False
    last3 = df.iloc[-3:]
    r3 = float(((last3["high"] - last3["low"]) / last3["close"]).mean())
    adr = avg_daily_range_pct(df)
    return r3 <= 0.6 * adr if adr > 0 else False


# ── Stage 2: MA stack / surfing ──────────────────────────────────────


def ma_stack(df: pd.DataFrame) -> dict[str, Any]:
    """MA alignment + surfing distance.

    ``aligned`` = EMA10 > EMA20 and positive EMA50 slope. The close-within-8%
    surfing check is applied by the caller (``score_bo_setup``).
    Returns dict with aligned flag, surfing distance (%), and EMAs.
    """
    close = df["close"]
    ema10 = close.ewm(span=10, adjust=False).mean().iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50_series = close.ewm(span=50, adjust=False).mean()
    if len(ema50_series) >= 6:
        ema50_slope = float(ema50_series.iloc[-1] - ema50_series.iloc[-6])
    else:
        ema50_slope = 0.0
    surfing = (float(close.iloc[-1]) - float(ema10)) / float(ema10) * 100.0
    aligned = bool(float(ema10) > float(ema20) and ema50_slope > 0)
    return {
        "aligned": aligned,
        "surfing_dist_pct": float(surfing),
        "ema10": float(ema10),
        "ema20": float(ema20),
        "ema50_slope": float(ema50_slope),
    }


# ── Stage 3: pivot via Gaussian KDE ──────────────────────────────────


def find_local_peaks(highs, radius: int = 2) -> list[tuple[int, float]]:
    """Local peak highs: bar whose high exceeds both sides within ``radius``."""
    highs = np.asarray(highs, dtype=float)
    n = len(highs)
    out: list[tuple[int, float]] = []
    for i in range(radius, n - radius):
        if highs[i] >= np.max(highs[i - radius : i]) and highs[i] >= np.max(
            highs[i + 1 : i + radius + 1]
        ):
            out.append((i, float(highs[i])))
    return out


def kde_pivot(
    peaks: list[tuple[int, float]],
    prices: float,
    bandwidth_pct: float = 0.03,
    range_lo: Optional[float] = None,
    range_hi: Optional[float] = None,
) -> Optional[float]:
    """Gaussian KDE mode over peak highs in the upper quartile of the range.

    Bandwidth = ``bandwidth_pct`` * current price. Peaks outside the optional
    consolidation range [range_lo, range_hi] are ignored. Returns the global
    KDE mode located within the upper quartile of the consolidation range.
    """
    if not peaks:
        return None
    values = np.asarray([float(p) for _, p in peaks], dtype=float)
    if range_lo is not None and range_hi is not None:
        values = values[(values >= range_lo) & (values <= range_hi)]
    if len(values) == 0:
        return None
    current = float(prices)
    h = bandwidth_pct * current
    if h <= 0:
        return None
    lo, hi = float(values.min()), float(values.max())
    if lo == hi:
        return lo
    grid = np.linspace(lo, hi, 400)
    density = np.zeros_like(grid)
    for v in values:
        density += np.exp(-0.5 * ((grid - v) / h) ** 2)
    q_lo = lo + 0.75 * (hi - lo)
    mask = grid >= q_lo
    if not mask.any():
        return float(grid[np.argmax(density)])
    return float(grid[mask][np.argmax(density[mask])])


# ── Stage 3: higher lows ─────────────────────────────────────────────


def find_local_lows(lows, radius: int = 2) -> list[int]:
    lows = np.asarray(lows, dtype=float)
    n = len(lows)
    out: list[int] = []
    for i in range(radius, n - radius):
        if lows[i] <= np.min(lows[i - radius : i]) and lows[i] <= np.min(
            lows[i + 1 : i + radius + 1]
        ):
            out.append(i)
    return out


def higher_lows(df: pd.DataFrame, end_idx: int, start_idx: Optional[int] = None) -> int:
    """Count of consecutive strictly higher lows leading into ``end_idx``.

    Swing lows (2-day radius) are found in [start_idx, end_idx]; the count
    walks backward from the most recent swing low while each prior low is
    strictly higher.
    """
    lows = df["low"].values
    lo = start_idx if start_idx is not None else 0
    if end_idx - lo + 1 < 5:
        return 0
    seg = lows[lo : end_idx + 1]
    local = find_local_lows(seg, radius=2)
    if len(local) < 2:
        return 1 if len(local) == 1 else 0
    count = 1
    for i in range(len(local) - 1, 0, -1):
        if seg[local[i]] > seg[local[i - 1]]:
            count += 1
        else:
            break
    return count


# ── Stage 3/4: volume signature ──────────────────────────────────────


def _pre_base_volume(df: pd.DataFrame, start_idx: int, lookback: int = 20) -> float:
    start = max(0, start_idx - lookback)
    seg = df["volume"].iloc[start:start_idx]
    if len(seg) == 0:
        seg = df["volume"].iloc[max(0, start_idx - 5) : start_idx]
    return float(seg.mean()) if len(seg) else 0.0


def _dryup_ratio(df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
    baseline = _pre_base_volume(df, start_idx)
    if baseline <= 0:
        return 1.0
    end_seg = df["volume"].iloc[max(start_idx, end_idx - 2) : end_idx + 1]
    return float(end_seg.mean()) / baseline


def volume_signature(
    df: pd.DataFrame,
    base: BoBase,
    breakout_idx: Optional[int] = None,
) -> dict[str, float]:
    """Dry-up ratio during the base + breakout surge vs pre-base baseline."""
    s, e = base.start_idx, base.end_idx
    dryup = _dryup_ratio(df, s, e)
    baseline = _pre_base_volume(df, s)
    idx = breakout_idx if breakout_idx is not None else len(df) - 1
    vol = float(df["volume"].iloc[idx])
    surge = vol / baseline if baseline > 0 else 0.0
    return {"dryup_ratio": dryup, "baseline_volume": baseline, "surge": surge}


# ── Base detection ───────────────────────────────────────────────────


def _build_base_candidate(
    df: pd.DataFrame, s: int, e: int, peak_idx: Optional[int] = None
) -> Optional[BoBase]:
    if e < 20:
        return None
    # The window starts at the structural peak (impulse/continuation high). The
    # anchor bar's high is the top of the prior move, not base resistance, so
    # exclude it from the base's own high/low envelope.
    start = s + 1 if peak_idx is not None and s == peak_idx else s
    win = df.iloc[start : e + 1]
    base_high = float(win["high"].max())
    base_low = float(win["low"].min())
    if base_high <= 0 or base_low <= 0:
        return None
    depth_pct = (base_high - base_low) / base_high * 100.0

    vci = vci_atr(df.iloc[: e + 1], short=5, medium=20)
    if vci > VCI_MAX:
        return None
    if not _narrow_three_day(df.iloc[: e + 1]):
        return None

    peaks = find_local_peaks(df["high"].values[s : e + 1], radius=2)
    if len(peaks) < 2:
        return None
    pivot = kde_pivot(
        peaks,
        prices=float(df["close"].iloc[e]),
        bandwidth_pct=0.03,
        range_lo=base_low,
        range_hi=base_high,
    )
    if pivot is None:
        return None
    if higher_lows(df, e, s) < 1:
        return None

    return BoBase(
        start_idx=s,
        end_idx=e,
        base_high=base_high,
        base_low=base_low,
        depth_pct=depth_pct,
        duration_days=e - s + 1,
        pivot=pivot,
        vci=vci,
        dryup_ratio=_dryup_ratio(df, s, e),
    )


def _dedup_bases(bases: list[BoBase]) -> list[BoBase]:
    """Drop overlapping bases; keep the latest-end base per region."""
    if not bases:
        return []
    ordered = sorted(bases, key=lambda b: (b.start_idx, b.end_idx))
    kept = [ordered[0]]
    for b in ordered[1:]:
        prev = kept[-1]
        if b.start_idx > prev.end_idx:
            kept.append(b)
        elif b.end_idx > prev.end_idx:
            kept[-1] = b
    return kept


def detect_bases(df: pd.DataFrame) -> list[BoBase]:
    """Detect valid consolidation bases (10-40d, VCI <= 0.65, KDE pivot).

    A base window starts at the most recent structural peak (the impulse
    high) — Qullamaggie bases begin right at the top of the prior move. The
    peak bar is excluded from the base's own high/low envelope by
    ``_build_base_candidate``.
    """
    n = len(df)
    if n < MIN_BARS:
        return []
    highs = df["high"].values
    candidates: list[BoBase] = []
    for e in range(BASE_MIN_DAYS, n):
        peak_idx = int(np.argmax(highs[: e + 1]))
        lo_s = max(peak_idx, e - BASE_MAX_DAYS + 1)
        hi_s = e - BASE_MIN_DAYS + 1
        best: Optional[BoBase] = None
        for s in range(lo_s, hi_s + 1):
            if s > e:
                continue
            base = _build_base_candidate(df, s, e, peak_idx)
            if base is None:
                continue
            if best is None or base.vci < best.vci:
                best = base
        if best is not None:
            candidates.append(best)
    return _dedup_bases(candidates)


# ── Stage 4: breakout trigger ────────────────────────────────────────


def detect_breakout(
    df: pd.DataFrame, base: BoBase, min_surge: float = SURGE_MIN
) -> Optional[dict[str, float]]:
    """Detect breakout above the pivot with a volume surge >= ``min_surge``.

    Returns dict with breakout_idx, rvol10, surge, surge_pct — or None when
    the trigger is not met (e.g. low-volume fakeout).
    """
    n = len(df)
    pivot = base.pivot
    baseline = _pre_base_volume(df, base.start_idx)
    candidates = [
        i for i in range(base.end_idx + 1, n) if float(df["close"].iloc[i]) > pivot
    ]
    if not candidates:
        return None
    idx = candidates[-1]
    if float(df["close"].iloc[-1]) <= pivot:
        return None
    vol = float(df["volume"].iloc[idx])
    surge = vol / baseline if baseline > 0 else 0.0
    if surge < min_surge:
        return None
    rvol10 = 0.0
    if idx >= 10:
        ten = float(df["volume"].iloc[idx - 10 : idx].mean())
        rvol10 = vol / ten if ten > 0 else 0.0
    return {
        "breakout_idx": idx,
        "rvol10": float(rvol10),
        "surge": float(surge),
        "surge_pct": float(surge) * 100.0,
    }


# ── Variant classification ───────────────────────────────────────────


def classify_variant(df: pd.DataFrame, bases: list[BoBase]) -> str:
    """Classify a setup: classic / lower_base / none.

    ``lower_base`` = two-base sequence where the newer base sits below the
    higher high reached after the first base completed, and price is above
    the second base's high but below that higher high.
    """
    if not bases:
        return "none"
    close = float(df["close"].iloc[-1])
    if len(bases) >= 2:
        a, b = bases[-2], bases[-1]
        if b.start_idx > a.end_idx:
            region_high = float(df["high"].iloc[a.end_idx + 1 : b.end_idx + 1].max())
            if b.base_high < region_high and close <= region_high * 1.01:
                return "lower_base"
    return "classic"


# ── Scoring ──────────────────────────────────────────────────────────


def score_bo_setup(
    df: pd.DataFrame,
    benchmark: Optional[pd.DataFrame] = None,
    *,
    symbol: str = "",
    exchange: str = "",
    as_of: Optional[date] = None,
) -> Optional[BoSetupRating]:
    """Score a stock for a Qullamaggie BO setup using pure math.

    Returns None for < ~90 bars; a 3★ rating for valid data with no
    base/breakout; 4-5★ only when every essential parameter passes and the
    volume surge / variant meet the rubric.
    """
    if df is None or len(df) < MIN_BARS:
        return None
    day = as_of or date.today()
    closes = df["close"].values

    impulse_pct = prior_impulse(closes)
    adr20_pct = avg_daily_range_pct(df)
    bases = detect_bases(df)
    base = bases[-1] if bases else None
    breakout = detect_breakout(df, base) if base is not None else None
    variant = classify_variant(df, bases) if base is not None else "none"

    # VCI is measured over the base window (through base.end_idx) — breakout
    # bars would inflate ATR5 and hide the contraction.
    vci_window = df.iloc[: base.end_idx + 1] if base is not None else df
    vci_ratio = vci_atr(vci_window, short=5, medium=20)
    mstack = ma_stack(df)
    surfing = mstack["surfing_dist_pct"]

    p_impulse = impulse_pct >= MIN_IMPULSE_PCT
    p_adr = passes_adr_envelope(adr20_pct)
    p_duration = base is not None and BASE_MIN_DAYS <= base.duration_days <= BASE_MAX_DAYS
    p_vci = vci_ratio <= VCI_MAX
    p_mastack = bool(mstack["aligned"] and -SURFING_MAX_PCT <= surfing <= SURFING_MAX_PCT)
    extension = surfing > SURFING_MAX_PCT
    p_pivot = base is not None and base.pivot > 0
    hl_count = higher_lows(df, base.end_idx, base.start_idx) if base is not None else 0
    p_hl = hl_count >= 1
    surge = breakout["surge"] if breakout else 0.0
    p_surge = breakout is not None and surge >= SURGE_MIN
    # Volume signature is a dual condition (research UT-06): base volume must
    # dry up (end-of-base ≤ 0.5× pre-base baseline) before the breakout surge.
    p_dryup = base is not None and base.dryup_ratio <= DRYUP_MAX

    essentials = [p_impulse, p_adr, p_duration, p_vci, p_mastack, p_pivot, p_hl, p_dryup, p_surge]
    if extension or not all(essentials):
        rating = 3
    elif variant == "lower_base":
        # lower_base is capped at 4★; 1.5x surge is its floor.
        rating = 4 if surge >= SURGE_MIN else 3
    elif variant == "classic":
        if surge >= SURGE_TEXTBOOK:
            rating = 5
        elif surge >= SURGE_STRONG:
            rating = 4
        else:
            rating = 3
    else:
        rating = 3

    # RS near highs boosts score; never a hard reject.
    rs_rating: Optional[float] = None
    if benchmark is not None and len(benchmark) >= 10:
        rs_line = compute_rs_line(df, benchmark)
        if len(rs_line) >= 5:
            rs_rating = compute_rs_rating(rs_line)
    if rating == 4 and variant == "classic" and rs_rating is not None and rs_rating >= 85.0:
        rating = 5

    breakout_idx = breakout["breakout_idx"] if breakout else None
    breakout_date: Optional[date] = None
    if breakout_idx is not None:
        bdate = df.index[breakout_idx]
        if isinstance(bdate, datetime):
            breakout_date = bdate.date()
        elif isinstance(bdate, date):
            breakout_date = bdate

    # 50-day SMA extension — secondary report field only, never a gate.
    sma50_extension_pct = 0.0
    if len(df) >= 50:
        sma50 = float(df["close"].iloc[-50:].mean())
        sma50_extension_pct = (float(df["close"].iloc[-1]) / sma50 - 1.0) * 100.0

    return BoSetupRating(
        symbol=symbol,
        exchange=exchange,
        variant=variant,  # type: ignore[arg-type]
        rating=rating,  # type: ignore[arg-type]
        label=BO_LABELS.get(rating, "sub_standard"),  # type: ignore[arg-type]
        prior_impulse=p_impulse,
        prior_impulse_pct=impulse_pct,
        adr20=p_adr,
        adr20_pct=adr20_pct,
        base_duration=p_duration,
        base_duration_days=base.duration_days if base else 0,
        vci=p_vci,
        vci_ratio=vci_ratio,
        ma_stack=p_mastack,
        surfing_dist_pct=surfing,
        pivot_kde=p_pivot,
        higher_lows=p_hl,
        higher_lows_count=hl_count,
        dryup=p_dryup,
        dryup_ratio=base.dryup_ratio if base else 1.0,
        volume_surge=p_surge,
        surge_pct=surge * 100.0,
        extension=extension,
        extension_pct=max(0.0, surfing - SURFING_MAX_PCT),
        sma50_extension_pct=sma50_extension_pct,
        base_high=base.base_high if base else 0.0,
        base_low=base.base_low if base else 0.0,
        pivot=base.pivot if base else 0.0,
        breakout_idx=breakout_idx,
        breakout_date=breakout_date,
        rvol10=breakout["rvol10"] if breakout else 0.0,
        rs_rating=rs_rating,
        as_of=day,
    )


def derive_near_miss(
    ratings: list[BoSetupRating],
    *,
    threshold: int = 7,
) -> list[BoNearMiss]:
    """Derive near-miss watchlist from ratings that are 3★ but close.

    Only considers ratings where ``rating == 3`` AND ``extension is False``
    (overextended setups are not near-misses).  A rating qualifies when it
    passed at least ``threshold`` of the 9 essentials (default 7, i.e. failed
    ≤ 2).

    The result is sorted closest-first: ``failed_count`` ascending, then
    ``rs_rating`` descending (``None`` last), then ``symbol``.
    """
    near: list[BoNearMiss] = []
    for r in ratings:
        if r.rating != 3 or r.extension:
            continue
        flags: dict[str, bool] = {
            "prior_impulse": r.prior_impulse,
            "adr20": r.adr20,
            "base_duration": r.base_duration,
            "vci": r.vci,
            "ma_stack": r.ma_stack,
            "pivot_kde": r.pivot_kde,
            "higher_lows": r.higher_lows,
            "dryup": r.dryup,
            "volume_surge": r.volume_surge,
        }
        passed = [k for k in ESSENTIAL_KEYS if flags.get(k, False)]
        failed = [k for k in ESSENTIAL_KEYS if k not in passed]
        if len(passed) < threshold:
            continue
        near.append(
            BoNearMiss(
                symbol=r.symbol,
                exchange=r.exchange,
                variant=r.variant,
                rating=3,
                passed_essentials=passed,
                failed_essentials=failed,
                passed_count=len(passed),
                failed_count=len(failed),
                dryup_ratio=r.dryup_ratio,
                surge_pct=r.surge_pct,
                surfing_dist_pct=r.surfing_dist_pct,
                pivot=r.pivot,
                breakout_date=r.breakout_date,
                rvol10=r.rvol10,
                rs_rating=r.rs_rating,
            )
        )
    near.sort(key=lambda n: (n.failed_count, -(n.rs_rating if n.rs_rating is not None else -1.0), n.symbol))
    return near


def screen_bucket(ratings: list[BoSetupRating]) -> BoScanBucket:
    """Bucket scored setups into 5★ / 4★ / 3★ envelopes."""
    five = [r for r in ratings if r.rating == 5]
    four = [r for r in ratings if r.rating == 4]
    three = [r for r in ratings if r.rating <= 3]
    return BoScanBucket(
        as_of=datetime.now(timezone.utc),
        ratings=ratings,
        five_star=five,
        four_star=four,
        three_star=three,
        near_miss=derive_near_miss(ratings),
        count=len(ratings),
        counts={"5": len(five), "4": len(four), "3": len(three)},
    )
