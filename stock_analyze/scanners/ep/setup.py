"""EP technical setup detection — pure math from OHLCV.

Event day = the highest-volume bar in the last ``EVENT_LOOKBACK_BARS``
(the gap/earnings shock). Features score the post-event setup:
- ``volume_spike`` — event volume >= ``spike_min`` x 50d average.
- ``pullback_contrast`` — a post-event pullback >= ``pullback_depth_pct``
  made on volume <= ``pullback_vol_ratio`` x event volume, with recovery.
- ``base_detected`` — a 5-40d base after the event: pivot high, ascending
  swing structure, volume contrast (pullback <= ``pullback_vol_ratio`` x
  event volume, up-leg >= 1.5x pullback avg).
- ``ema_support`` — price above EMA9/20/50 with the stack ordered and
  >= 2 of the 3 EMAs touched-and-held since the event.
- ``vwap_support`` — anchored VWAP from the event day; falls back to the
  post-event pivot (higher high) anchor when the event anchor shows none.

All thresholds live in ``EpSetupThresholds`` and are editable as scanner
vars. Never raises on short/malformed frames — returns all-False features.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from stock_analyze.models.ep import EpSetupFeatures
from stock_analyze.scanners.bo.metrics import higher_lows

EVENT_LOOKBACK_BARS = 63
MIN_BARS = 60

FEATURE_KEYS = [
    "base_detected",
    "volume_spike",
    "pullback_contrast",
    "ema_support",
    "vwap_support",
]


class EpSetupThresholds(BaseModel):
    """Editable thresholds for the EP technical setup test."""

    spike_min: float = Field(default=3.0, description="Event volume x vs 50d avg")
    pullback_vol_ratio: float = Field(default=0.5, description="Pullback volume vs event volume")
    pullback_depth_pct: float = Field(default=10.0, description="Min post-event pullback depth %")
    ema_touch_pct: float = Field(default=2.0, description="EMA touch tolerance %")
    vwap_touch_pct: float = Field(default=1.5, description="VWAP touch tolerance %")
    base_min_days: int = Field(default=5, description="Min base duration after event")
    base_max_days: int = Field(default=40, description="Max base duration after event")


DEFAULT_THRESHOLDS = EpSetupThresholds()


# ── event day ──────────────────────────────────────────────────────


def _event_idx(df: pd.DataFrame, lookback: int = EVENT_LOOKBACK_BARS) -> Optional[int]:
    """Index of the highest-volume bar in the last ``lookback`` bars."""
    if df is None or len(df) < MIN_BARS:
        return None
    tail = df["volume"].iloc[-min(lookback, len(df)):]
    rel = int(np.argmax(tail.values))
    return len(df) - len(tail) + rel


# ── volume spike ───────────────────────────────────────────────────


def _detect_volume_spike(df: pd.DataFrame, event_idx: int, thr: EpSetupThresholds) -> tuple[bool, float]:
    event_vol = float(df["volume"].iloc[event_idx])
    hist = df["volume"].iloc[max(0, event_idx - 50):event_idx]
    if len(hist) < 10 or event_vol <= 0:
        return False, 0.0
    avg = float(hist.mean())
    if avg <= 0:
        return False, 0.0
    ratio = event_vol / avg
    return ratio >= thr.spike_min, ratio


# ── pullback contrast ──────────────────────────────────────────────


def _detect_pullback(df: pd.DataFrame, event_idx: int, thr: EpSetupThresholds) -> tuple[bool, float]:
    start = event_idx + 1
    win = df.iloc[start:]
    if len(win) < 3:
        return False, 0.0
    post_high = float(win["high"].max())
    post_low = float(win["low"].min())
    if post_high <= 0:
        return False, 0.0
    depth = (post_high - post_low) / post_high * 100.0
    if depth < thr.pullback_depth_pct:
        return False, 0.0
    event_vol = float(df["volume"].iloc[event_idx])
    if event_vol <= 0:
        return False, 0.0
    pb_avg = float(win["volume"].mean())
    ratio = pb_avg / event_vol
    if pb_avg > thr.pullback_vol_ratio * event_vol:
        return False, ratio
    if float(df["close"].iloc[-1]) <= post_low:
        return False, ratio
    return True, ratio


# ── base detection ─────────────────────────────────────────────────


def _detect_base(df: pd.DataFrame, event_idx: int, thr: EpSetupThresholds) -> bool:
    """Valid post-event base: pivot high + higher lows + volume contrast.

    A base is any 5-40d window starting the bar after the event. The pivot
    (window's highest high) must be followed by a low-volume pullback and a
    higher-volume up-leg that recovers above the pullback low.
    """
    start = event_idx + 1
    max_end = min(start + thr.base_max_days, len(df))
    if max_end - start < thr.base_min_days:
        return False
    event_vol = float(df["volume"].iloc[event_idx])
    if event_vol <= 0:
        return False
    for end in range(start + thr.base_min_days - 1, max_end):
        win = df.iloc[start:end + 1]
        pivot_rel = int(np.argmax(win["high"].values))
        if pivot_rel >= len(win) - 1:
            continue  # need bars after the pivot
        if higher_lows(df, end, start) < 1:
            continue
        post = win.iloc[pivot_rel + 1:]
        low_rel = int(np.argmin(post["low"].values))
        pullback = post.iloc[:low_rel + 1]
        upleg = post.iloc[low_rel + 1:]
        if len(pullback) < 1 or len(upleg) < 1:
            continue
        pb_avg = float(pullback["volume"].mean())
        up_avg = float(upleg["volume"].mean())
        if pb_avg <= 0 or up_avg < 1.5 * pb_avg:
            continue
        if pb_avg > thr.pullback_vol_ratio * event_vol:
            continue
        pullback_low_idx = start + pivot_rel + 1 + low_rel
        if float(win["close"].iloc[-1]) <= float(df["low"].iloc[pullback_low_idx]):
            continue  # no recovery above the pullback low
        return True
    return False


# ── EMA support ────────────────────────────────────────────────────


def _detect_ema_support(df: pd.DataFrame, event_idx: int, thr: EpSetupThresholds) -> tuple[bool, bool]:
    if len(df) < 50:
        return False, False
    close = df["close"]
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    cur = float(close.iloc[-1])
    e9, e20, e50 = float(ema9.iloc[-1]), float(ema20.iloc[-1]), float(ema50.iloc[-1])
    aligned = bool(cur > e9 > e20 > e50)
    if not aligned:
        return False, aligned
    tol = thr.ema_touch_pct / 100.0
    post = df.iloc[event_idx:]
    lows = post["low"].values
    closes = post["close"].values
    held = 0
    for ema_vals in (
        ema9.iloc[event_idx:].values,
        ema20.iloc[event_idx:].values,
        ema50.iloc[event_idx:].values,
    ):
        if any(lows[i] <= ema_vals[i] * (1 + tol) and closes[i] > ema_vals[i] for i in range(len(post))):
            held += 1
    return held >= 2, aligned


# ── VWAP support ───────────────────────────────────────────────────


def _anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """Cumulative VWAP from ``anchor_idx`` forward (typical-price weighted).

    Only bars at/after the anchor are weighted — a truly anchored VWAP.
    """
    seg = df.iloc[anchor_idx:]
    tp = (seg["high"] + seg["low"] + seg["close"]) / 3.0
    cum_pv = (tp * seg["volume"]).cumsum()
    cum_v = seg["volume"].cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


def _vwap_support_at(df: pd.DataFrame, anchor_idx: int, thr: EpSetupThresholds) -> bool:
    """True when a post-anchor bar low dipped within ``vwap_touch_pct`` of
    the anchored VWAP, closed back above, and the last close > VWAP."""
    if anchor_idx >= len(df) - 1:
        return False
    vwap = _anchored_vwap(df, anchor_idx)
    post = df.iloc[anchor_idx:]
    tol = thr.vwap_touch_pct / 100.0
    lows = post["low"].values
    closes = post["close"].values
    vwap_vals = vwap.values
    if float(closes[-1]) <= float(vwap_vals[-1]):
        return False
    return any(
        lows[i] <= vwap_vals[i] * (1 + tol) and closes[i] > vwap_vals[i]
        for i in range(len(post))
    )


def _detect_vwap(df: pd.DataFrame, event_idx: int, thr: EpSetupThresholds) -> tuple[str, bool]:
    """Event anchor first; fall back to the post-event pivot (higher high)."""
    if _vwap_support_at(df, event_idx, thr):
        return "event", True
    post = df.iloc[event_idx:]
    if len(post) >= 2:
        pivot_rel = int(np.argmax(post["high"].values))
        pivot_idx = event_idx + pivot_rel
        if pivot_idx != event_idx and _vwap_support_at(df, pivot_idx, thr):
            return "pivot", True
    return "none", False


# ── scoring ────────────────────────────────────────────────────────


def score_ep_setup(
    df: Optional[pd.DataFrame],
    *,
    enabled: Optional[dict[str, bool]] = None,
    thresholds: Optional[EpSetupThresholds] = None,
    symbol: str = "",
    exchange: str = "",
    as_of: Optional[date] = None,
) -> EpSetupFeatures:
    """Score the EP technical setup from OHLCV (pure math).

    ``enabled`` maps feature key → toggle; ``features_held`` counts only
    enabled features that hold (None = all enabled). Short/None frames
    return an all-False snapshot rather than raising.
    """
    thr = thresholds or DEFAULT_THRESHOLDS
    empty = lambda: EpSetupFeatures(  # noqa: E731
        symbol=symbol, exchange=exchange, as_of=as_of or date.today(),
    )
    if df is None or len(df) < MIN_BARS:
        return empty()
    event_idx = _event_idx(df)
    if event_idx is None:
        return empty()

    spike, spike_ratio = _detect_volume_spike(df, event_idx, thr)
    base = _detect_base(df, event_idx, thr)
    pull, pull_ratio = _detect_pullback(df, event_idx, thr)
    ema, ema_aligned = _detect_ema_support(df, event_idx, thr)
    vwap_anchor, vwap = _detect_vwap(df, event_idx, thr)

    flags = {
        "base_detected": base,
        "volume_spike": spike,
        "pullback_contrast": pull,
        "ema_support": ema,
        "vwap_support": vwap,
    }
    enabled_map = (
        {k: True for k in FEATURE_KEYS}
        if enabled is None
        else {k: bool(enabled.get(k, True)) for k in FEATURE_KEYS}
    )
    held = sum(1 for k in FEATURE_KEYS if flags[k] and enabled_map[k])

    return EpSetupFeatures(
        symbol=symbol,
        exchange=exchange,
        event_idx=event_idx,
        base_detected=base,
        volume_spike=spike,
        pullback_contrast=pull,
        ema_support=ema,
        vwap_support=vwap,
        features_held=held,
        event_volume_ratio=round(spike_ratio, 4),
        pullback_vol_ratio=round(pull_ratio, 4),
        ema_stack_aligned=ema_aligned,
        vwap_anchor=vwap_anchor,
        as_of=as_of or date.today(),
    )


__all__ = [
    "DEFAULT_THRESHOLDS",
    "EVENT_LOOKBACK_BARS",
    "FEATURE_KEYS",
    "MIN_BARS",
    "EpSetupThresholds",
    "score_ep_setup",
]
