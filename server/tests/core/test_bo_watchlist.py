"""Unit tests for BO watchlist funnel gate functions."""

import pytest
from datetime import date

from stock_analyze.models.bo import BoSetupRating
from stock_analyze.scanners.bo.watchlist import (
    WATCHLIST_PROFILES,
    apply_funnel,
    compute_q_base,
    g2_adv_dollar,
    g3_ema10_proximity,
    g4_base_duration,
    g5_volume_dryup,
    q_base_to_stars,
    tradable_count,
)


def _make_rating(**kwargs) -> BoSetupRating:
    """Build a minimal BoSetupRating with default passable funnel values."""
    defaults = dict(
        symbol="TEST",
        exchange="NASDAQ",
        variant="classic",
        rating=4,
        label="strong",
        prior_impulse=True,
        prior_impulse_pct=50.0,
        adr20=True,
        adr20_pct=6.0,
        base_duration=True,
        base_duration_days=20,
        vci=True,
        vci_ratio=0.52,
        ma_stack=True,
        surfing_dist_pct=2.0,
        pivot_kde=True,
        higher_lows=True,
        higher_lows_count=2,
        dryup=True,
        dryup_ratio=0.4,
        volume_surge=True,
        surge_pct=320.0,
        extension=False,
        extension_pct=0.0,
        adv_20d=60_000_000,
        ema10_dist_pct=3.0,
        ema10_rising=True,
        dryup_vol_ratio=0.4,
        tightness=0.5,
        as_of=date.today(),
    )
    defaults.update(kwargs)
    return BoSetupRating(**defaults)


# ── Profile definitions ──────────────────────────────────────────────


class TestProfiles:
    def test_best_has_adv_50m(self):
        assert WATCHLIST_PROFILES["best"]["adv"] == 50_000_000

    def test_best_has_ema_5(self):
        assert WATCHLIST_PROFILES["best"]["ema"] == 5.0

    def test_best_has_dryup_disabled(self):
        assert WATCHLIST_PROFILES["best"]["dryup"] == 0.0

    def test_best_has_base_40(self):
        assert WATCHLIST_PROFILES["best"]["base"] == 40

    def test_moderate_lose_has_adv_50m(self):
        assert WATCHLIST_PROFILES["moderate-lose"]["adv"] == 50_000_000

    def test_moderate_lose_has_ema_8(self):
        assert WATCHLIST_PROFILES["moderate-lose"]["ema"] == 8.0

    def test_widen_has_adv_30m(self):
        assert WATCHLIST_PROFILES["widen"]["adv"] == 30_000_000

    def test_widen_has_ema_8(self):
        assert WATCHLIST_PROFILES["widen"]["ema"] == 8.0

    def test_three_profiles_defined(self):
        assert set(WATCHLIST_PROFILES.keys()) == {"best", "moderate-lose", "widen"}


# ── Gate functions ───────────────────────────────────────────────────


class TestG2AdvDollar:
    def test_passes_above_floor(self):
        assert g2_adv_dollar(60_000_000, 50_000_000) is True

    def test_fails_below_floor(self):
        assert g2_adv_dollar(30_000_000, 50_000_000) is False

    def test_passes_at_floor(self):
        assert g2_adv_dollar(50_000_000, 50_000_000) is True

    def test_zero_adv_fails(self):
        assert g2_adv_dollar(0.0, 50_000_000) is False


class TestG3Ema10Proximity:
    def test_passes_within_max(self):
        assert g3_ema10_proximity(4.5, True, 5.0) is True

    def test_fails_above_max(self):
        assert g3_ema10_proximity(8.5, True, 8.0) is False

    def test_passes_at_boundary(self):
        assert g3_ema10_proximity(5.0, True, 5.0) is True

    def test_fails_when_ema_not_rising(self):
        assert g3_ema10_proximity(3.0, False, 5.0) is False

    def test_fails_both(self):
        assert g3_ema10_proximity(6.0, False, 5.0) is False

    def test_ema50_boundary_should_pass(self):
        """5.0% should pass for best profile."""
        assert g3_ema10_proximity(5.0, True, 5.0) is True

    def test_ema51_should_fail(self):
        """5.01% should fail for best profile."""
        assert g3_ema10_proximity(5.01, True, 5.0) is False


class TestG4BaseDuration:
    def test_passes_in_range(self):
        assert g4_base_duration(20, 40) is True

    def test_fails_too_short(self):
        assert g4_base_duration(3, 40) is False

    def test_fails_too_long(self):
        assert g4_base_duration(45, 40) is False

    def test_passes_at_min(self):
        assert g4_base_duration(5, 40) is True

    def test_passes_at_max(self):
        assert g4_base_duration(40, 40) is True

    def test_zero_duration_fails(self):
        assert g4_base_duration(0, 40) is False


class TestG5VolumeDryup:
    def test_passes_below_ratio(self):
        assert g5_volume_dryup(0.3, 0.5) is True

    def test_fails_above_ratio(self):
        assert g5_volume_dryup(0.8, 0.5) is False

    def test_passes_when_disabled(self):
        assert g5_volume_dryup(10.0, None) is True

    def test_passes_at_ratio(self):
        assert g5_volume_dryup(0.5, 0.5) is True


# ── Q_base scoring ───────────────────────────────────────────────────


class TestQBaseToStars:
    def test_90_is_five_star(self):
        assert q_base_to_stars(90) == 5

    def test_89_is_four_star(self):
        assert q_base_to_stars(89) == 4

    def test_75_is_four_star(self):
        assert q_base_to_stars(75) == 4

    def test_74_is_three_star(self):
        assert q_base_to_stars(74) == 3

    def test_60_is_three_star(self):
        assert q_base_to_stars(60) == 3

    def test_59_is_zero(self):
        assert q_base_to_stars(59) == 0

    def test_100_is_five_star(self):
        assert q_base_to_stars(100) == 5

    def test_0_is_zero(self):
        assert q_base_to_stars(0) == 0

    def test_negative_is_zero(self):
        assert q_base_to_stars(-1) == 0


class TestComputeQBase:
    def test_max_score(self):
        score = compute_q_base(vci=0.4, hl=4, tightness=0.3,
                               prior_pct=70.0, dryup=0.2, surfing=0.5)
        assert score == 100

    def test_min_score(self):
        score = compute_q_base(vci=0.8, hl=0, tightness=2.0,
                               prior_pct=20.0, dryup=0.8, surfing=5.0)
        assert score == 0

    def test_mid_range(self):
        """Realistic mid-range candidate should score 60-90."""
        score = compute_q_base(vci=0.52, hl=2, tightness=0.7,
                               prior_pct=45.0, dryup=0.4, surfing=2.0)
        assert 60 <= score <= 90

    def test_vci_bands(self):
        assert compute_q_base(vci=0.49, hl=0, tightness=2.0, prior_pct=0, dryup=1.0, surfing=5.0) >= 25
        assert compute_q_base(vci=0.59, hl=0, tightness=2.0, prior_pct=0, dryup=1.0, surfing=5.0) >= 20

    def test_tightness_bands(self):
        assert compute_q_base(vci=0.8, hl=0, tightness=0.55, prior_pct=0, dryup=1.0, surfing=5.0) >= 15
        assert compute_q_base(vci=0.8, hl=0, tightness=0.70, prior_pct=0, dryup=1.0, surfing=5.0) >= 10

    def test_prior_pct_bands(self):
        assert compute_q_base(vci=0.8, hl=0, tightness=2.0, prior_pct=65.0, dryup=1.0, surfing=5.0) >= 15
        assert compute_q_base(vci=0.8, hl=0, tightness=2.0, prior_pct=35.0, dryup=1.0, surfing=5.0) >= 10

    def test_dryup_bands(self):
        assert compute_q_base(vci=0.8, hl=0, tightness=2.0, prior_pct=0, dryup=0.25, surfing=5.0) >= 10
        assert compute_q_base(vci=0.8, hl=0, tightness=2.0, prior_pct=0, dryup=0.35, surfing=5.0) >= 8

    def test_surfing_bands(self):
        assert compute_q_base(vci=0.8, hl=0, tightness=2.0, prior_pct=0, dryup=1.0, surfing=1.0) >= 5
        assert compute_q_base(vci=0.8, hl=0, tightness=2.0, prior_pct=0, dryup=1.0, surfing=3.0) >= 1


# ── apply_funnel ─────────────────────────────────────────────────────


class TestApplyFunnel:
    def test_textbook_survives_best(self):
        r = _make_rating()
        result = apply_funnel([r], "best")
        assert len(result.survivors) == 1
        assert result.survivors[0]["symbol"] == "TEST"
        assert result.survivors[0]["stars"] >= 3

    def test_low_adv_rejected(self):
        r = _make_rating(adv_20d=30_000_000)
        result = apply_funnel([r], "best")
        assert len(result.survivors) == 0

    def test_high_ema_rejected_best(self):
        r = _make_rating(ema10_dist_pct=5.5)
        result = apply_funnel([r], "best")
        assert len(result.survivors) == 0

    def test_high_ema_passes_moderate_lose(self):
        r = _make_rating(ema10_dist_pct=7.0)
        result = apply_funnel([r], "moderate-lose")
        assert len(result.survivors) == 1

    def test_low_adv_passes_widen(self):
        r = _make_rating(adv_20d=40_000_000)
        result = apply_funnel([r], "widen")
        assert len(result.survivors) == 1

    def test_no_prior_impulse_rejected(self):
        r = _make_rating(prior_impulse=False)
        result = apply_funnel([r], "best")
        assert len(result.survivors) == 0

    def test_gate_counts(self):
        r = _make_rating()
        result = apply_funnel([r], "best")
        assert result.gate["passed"]["g1_impulse"] == 1
        assert result.gate["passed"]["g2_adv"] == 1
        assert result.gate["passed"]["g3_ema10"] == 1

    def test_tradable_count_filters_low_stars(self):
        """Low q_base (< 60) rating should not appear in survivors."""
        r = _make_rating(
            vci_ratio=0.8, higher_lows_count=0, tightness=2.0,
            prior_impulse_pct=5.0, dryup_vol_ratio=0.9, surfing_dist_pct=6.0,
        )
        result = apply_funnel([r], "best")
        assert len(result.survivors) == 0

    def test_dict_input_works(self):
        r = _make_rating().model_dump()
        result = apply_funnel([r], "best")
        assert len(result.survivors) == 1

    def test_tradable_count_helper(self):
        survivors = [{"stars": 5}, {"stars": 4}, {"stars": 3}, {"stars": 0}]
        assert tradable_count(survivors) == 3


# ── Multiple survivors ───────────────────────────────────────────────


class TestApplyFunnelMultiple:
    def test_best_profile_typical_candidates(self):
        ratings = [
            _make_rating(symbol="A", prior_impulse_pct=55.0, vci_ratio=0.48),
            _make_rating(symbol="B", prior_impulse_pct=35.0, vci_ratio=0.60),
            _make_rating(symbol="C", prior_impulse_pct=45.0, vci_ratio=0.55),
        ]
        result = apply_funnel(ratings, "best")
        assert len(result.survivors) == 3
        # Should be sorted by q_base descending
        assert result.survivors[0]["q_base"] >= result.survivors[-1]["q_base"]
