"""Unit tests for BO metrics — UT-01..06 + EC-01..06 with synthetic OHLCV."""

import numpy as np
import pandas as pd
import pytest

from bo_fixtures import make_scenario, _make_bo_series, _make_garbage_series

from stock_analyze.scanners.bo.gates import passes_adr_envelope
from stock_analyze.scanners.bo.metrics import (
    avg_daily_range_pct,
    classify_variant,
    detect_bases,
    detect_breakout,
    find_local_peaks,
    higher_lows,
    kde_pivot,
    ma_stack,
    prior_impulse,
    score_bo_setup,
    screen_bucket,
    vci_atr,
    volume_signature,
)

SCORE_ARGS = {"symbol": "TEST", "exchange": "NYSE"}


def _score(kind: str, **overrides):
    df = make_scenario(kind)
    return score_bo_setup(df, **{**SCORE_ARGS, **overrides})


# ── UT-01: prior impulse ─────────────────────────────────────────────


def test_prior_impulse_strong():
    df = make_scenario("textbook_classic")
    assert prior_impulse(df["close"].values) >= 40.0


def test_prior_impulse_low_rejected():
    df = make_scenario("low_impulse")  # 15% advance
    assert prior_impulse(df["close"].values) < 30.0


# ── UT-02: ADR20 envelope [FALSE, TRUE, FALSE] ───────────────────────


def test_adr20_envelope_passes_mid_range():
    assert passes_adr_envelope(6.0) is True


def test_adr20_envelope_rejects_sluggish():
    assert passes_adr_envelope(3.0) is False


def test_adr20_envelope_rejects_wildcard():
    assert passes_adr_envelope(14.0) is False


def test_adr20_measured_within_envelope():
    df = make_scenario("textbook_classic")
    assert 4.0 <= avg_daily_range_pct(df) <= 12.0


# ── UT-03: VCI contraction ───────────────────────────────────────────


def test_vci_contraction_below_max():
    df = make_scenario("textbook_classic")
    base = detect_bases(df)[0]
    assert vci_atr(df.iloc[: base.end_idx + 1]) <= 0.65


def test_vci_garbage_above_max():
    df = make_scenario("garbage")
    assert vci_atr(df) > 0.65


# ── UT-04: MA stack / surfing ────────────────────────────────────────


def test_mastack_aligned_with_surfing():
    df = make_scenario("textbook_classic")
    stack = ma_stack(df)
    assert stack["aligned"] is True
    assert -8.0 <= stack["surfing_dist_pct"] <= 8.0


def test_surfing_overextended_clamps_rating():
    r = _score("extended")  # close > 8% above EMA10
    assert r is not None
    assert r.extension is True
    assert r.rating == 3


# ── UT-05: KDE pivot ─────────────────────────────────────────────────


def test_find_local_peaks():
    highs = np.array([1.0, 1.0, 5.0, 1.0, 1.0, 4.0, 1.0, 1.0])
    peaks = find_local_peaks(highs, radius=2)
    assert (2, 5.0) in peaks
    assert (5, 4.0) in peaks


def test_kde_pivot_mode_in_upper_quartile():
    peaks = [(0, 100.0), (1, 100.5), (2, 101.0), (3, 100.0), (4, 100.8), (5, 99.0), (6, 101.2)]
    pivot = kde_pivot(peaks, prices=101.0, bandwidth_pct=0.03)
    assert pivot is not None
    # Upper quartile of [99.0, 101.2] is ~100.65 — mode must sit there.
    assert pivot >= 100.65


def test_kde_pivot_none_for_empty():
    assert kde_pivot([], prices=100.0) is None


def test_kde_pivot_filters_out_of_range():
    peaks = [(0, 90.0), (1, 100.0), (2, 101.0), (3, 99.0)]
    pivot = kde_pivot(peaks, prices=100.0, bandwidth_pct=0.03, range_lo=95.0, range_hi=105.0)
    assert pivot is not None
    assert pivot > 99.0


# ── UT-06: volume signature (dry-up then surge) ──────────────────────


def test_volume_dryup_and_surge():
    df = make_scenario("textbook_classic")
    base = detect_bases(df)[0]
    sig = volume_signature(df, base)
    assert sig["dryup_ratio"] <= 0.6
    assert sig["surge"] >= 1.5
    assert sig["baseline_volume"] > 0


def test_detect_breakout_golden():
    df = make_scenario("textbook_classic")
    base = detect_bases(df)[0]
    brk = detect_breakout(df, base)
    assert brk is not None
    assert brk["breakout_idx"] == len(df) - 1
    assert brk["surge"] >= 3.0


def test_detect_breakout_none_when_surge_too_low():
    df = make_scenario("near_miss")
    base = detect_bases(df)[0]
    assert detect_breakout(df, base) is None


# ── EC-01: overextension ─────────────────────────────────────────────


def test_ec01_overextended_clamped():
    r = _score("extended")
    assert r is not None
    assert r.extension is True
    assert r.rating == 3


# ── EC-02: low-volume fakeout ────────────────────────────────────────


def test_ec02_low_volume_fakeout():
    r = _score("near_miss")
    assert r is not None
    assert r.volume_surge is False
    assert r.rating == 3


def test_no_dryup_rejected():
    """UT-06 dual condition: a surge without prior base dry-up stays 3★."""
    df = make_scenario("no_dryup")
    base = detect_bases(df)[0]
    assert base.dryup_ratio > 0.5
    r = score_bo_setup(df, **SCORE_ARGS)
    assert r is not None
    assert r.rating == 3


# ── EC-03: stale base (60d) ──────────────────────────────────────────


def test_ec03_stale_base_rejected():
    r = _score("stale_base")
    assert r is not None
    assert r.rating == 3
    assert r.base_duration_days == 0  # no valid base forms


# ── EC-04: V-shaped rebound ──────────────────────────────────────────


def test_ec04_vshape_breakout_rejected():
    df = make_scenario("vshape")
    r = score_bo_setup(df, **SCORE_ARGS)
    assert r is not None
    assert r.rating == 3
    assert ma_stack(df)["aligned"] is False


# ── EC-05: ADR > 12% wildcard ────────────────────────────────────────


def test_ec05_high_adr_rejected():
    r = _score("high_adr")
    assert r is not None
    assert r.adr20 is False
    assert r.rating == 3


# ── EC-06: negative 50d slope ────────────────────────────────────────


def test_ec06_negative_ema50_slope():
    df = make_scenario("downtrend")
    r = score_bo_setup(df, **SCORE_ARGS)
    assert r is not None
    assert ma_stack(df)["ema50_slope"] < 0
    assert r.rating == 3


# ── Golden artifacts ─────────────────────────────────────────────────


def test_detect_bases_golden():
    df = make_scenario("textbook_classic")
    bases = detect_bases(df)
    assert len(bases) == 1
    b = bases[0]
    assert b.start_idx == 69
    assert b.end_idx == 89
    assert b.duration_days == 21
    assert 150.0 <= b.pivot <= 156.0
    assert b.vci <= 0.65
    assert b.dryup_ratio <= 0.6


def test_volume_signature_golden():
    df = make_scenario("textbook_classic")
    base = detect_bases(df)[0]
    sig = volume_signature(df, base)
    assert sig["dryup_ratio"] == pytest.approx(0.43, abs=0.02)
    assert sig["surge"] == pytest.approx(3.5, abs=0.05)


def test_prior_impulse_golden():
    df = make_scenario("textbook_classic")
    assert prior_impulse(df["close"].values) == pytest.approx(45.65, abs=0.1)


def test_sma50_extension_report_field():
    """Secondary report field (plan): close distance from 50d SMA, never a gate."""
    df = make_scenario("textbook_classic")
    r = score_bo_setup(df, **SCORE_ARGS)
    assert r is not None
    assert isinstance(r.sma50_extension_pct, float)
    assert r.sma50_extension_pct >= 0.0


# ── Classify variant ─────────────────────────────────────────────────


def test_classify_variant_lower_base():
    df = make_scenario("lower_base")
    bases = detect_bases(df)
    assert len(bases) >= 2
    assert classify_variant(df, bases) == "lower_base"


def test_classify_variant_classic():
    df = make_scenario("textbook_classic")
    bases = detect_bases(df)
    assert classify_variant(df, bases) == "classic"


# ── Mini-universe screen ─────────────────────────────────────────────


MINI_UNIVERSE = {
    "textbook_classic": 5,
    "classic_strong": 4,
    "lower_base": 4,
    "near_miss": 3,
    "no_dryup": 3,
    "no_base": 3,
    "extended": 3,
    "garbage": 3,
    "stale_base": 3,
    "low_impulse": 3,
    "high_adr": 3,
    "vshape": 3,
    "downtrend": 3,
}


def test_mini_universe_ratings():
    for kind, expected in MINI_UNIVERSE.items():
        r = _score(kind)
        assert r is not None, kind
        assert r.rating == expected, f"{kind}: expected {expected}, got {r.rating}"


def test_screen_bucket_counts():
    ratings = [_score(k) for k in MINI_UNIVERSE]
    bucket = screen_bucket(ratings)
    assert bucket.count == len(MINI_UNIVERSE)
    assert bucket.counts["5"] == 1
    assert bucket.counts["4"] == 2
    assert bucket.counts["3"] == len(MINI_UNIVERSE) - 3
