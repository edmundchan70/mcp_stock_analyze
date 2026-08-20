"""Seam: score_ep_setup computes the 5 EP technical features from OHLCV."""

from __future__ import annotations

from stock_analyze.scanners.ep.setup import (
    FEATURE_KEYS,
    EpSetupThresholds,
    score_ep_setup,
)

from ep_fixtures import (
    make_mild_spike_series,
    make_no_base_series,
    make_no_pullback_series,
    make_short_series,
    make_vwap_fallback_series,
    make_ep_textbook,
)


def test_textbook_series_holds_all_features():
    features = score_ep_setup(make_ep_textbook(), symbol="AA", exchange="NASDAQ")
    assert features.event_idx == 50
    assert features.volume_spike is True
    assert features.pullback_contrast is True
    assert features.base_detected is True
    assert features.ema_support is True
    assert features.vwap_support is True
    assert features.features_held == 5
    assert features.event_volume_ratio >= 3.0
    assert features.ema_stack_aligned is True


def test_volume_spike_holds_and_measures_ratio():
    features = score_ep_setup(make_ep_textbook())
    assert features.volume_spike is True
    assert features.event_volume_ratio == 4.0


def test_volume_spike_fails_on_mild_event():
    features = score_ep_setup(make_mild_spike_series())
    assert features.volume_spike is False
    assert features.event_volume_ratio == 1.5


def test_pullback_contrast_fails_on_flat_after_event():
    features = score_ep_setup(make_no_pullback_series())
    assert features.pullback_contrast is False
    assert features.pullback_vol_ratio == 0.0


def test_base_detection_fails_without_consolidation():
    features = score_ep_setup(make_no_base_series())
    assert features.base_detected is False


def test_enabled_toggles_exclude_disabled_features_from_held():
    features = score_ep_setup(
        make_ep_textbook(),
        enabled={"volume_spike": False, "base_detected": False},
    )
    # 3 of 5 features still hold; disabled ones don't count
    assert features.features_held == 3
    # the underlying booleans are still measured
    assert features.volume_spike is True


def test_disabled_all_features_yields_zero_held():
    features = score_ep_setup(make_ep_textbook(), enabled={k: False for k in FEATURE_KEYS})
    assert features.features_held == 0


def test_vwap_anchor_falls_back_to_pivot_when_event_shows_no_support():
    features = score_ep_setup(make_vwap_fallback_series())
    assert features.vwap_support is True
    assert features.vwap_anchor == "pivot"


def test_short_frame_returns_all_false():
    features = score_ep_setup(make_short_series())
    assert features.event_idx is None
    assert features.features_held == 0
    assert not any(
        [features.base_detected, features.volume_spike, features.pullback_contrast,
         features.ema_support, features.vwap_support]
    )


def test_none_frame_returns_all_false():
    features = score_ep_setup(None)
    assert features.event_idx is None
    assert features.features_held == 0


def test_keep_if_any_boundary_at_least_one_held():
    features = score_ep_setup(
        make_ep_textbook(),
        enabled={
            "base_detected": True,
            "volume_spike": False,
            "pullback_contrast": False,
            "ema_support": False,
            "vwap_support": False,
        },
    )
    # only base_detected enabled and it holds
    assert features.features_held == 1
    assert features.features_held >= 1


def test_partial_enabled_dict_leaves_unspecified_features_on():
    # a partial ``enabled`` dict defaults unspecified features to enabled
    features = score_ep_setup(make_ep_textbook(), enabled={"base_detected": True})
    assert features.features_held == 5


def test_custom_thresholds_change_volume_spike():
    features = score_ep_setup(
        make_ep_textbook(),
        thresholds=EpSetupThresholds(spike_min=4.5),
    )
    assert features.volume_spike is False
