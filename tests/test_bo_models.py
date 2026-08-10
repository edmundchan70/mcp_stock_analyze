"""Tests for BO Pydantic model validation."""

import pytest
from datetime import date
from pydantic import ValidationError

from stock_analyze.models.bo import (
    BoBase,
    BoEnrichedBucket,
    BoNearMiss,
    BoRatedBucket,
    BoRatedStock,
    BoScanBucket,
    BoSetupRating,
)


class TestBoBase:
    def test_bo_base_valid(self):
        b = BoBase(
            start_idx=70,
            end_idx=89,
            base_high=151.4,
            base_low=145.0,
            depth_pct=4.2,
            duration_days=20,
            pivot=150.7,
            vci=0.52,
            dryup_ratio=0.4,
        )
        assert b.start_idx == 70
        assert b.end_idx == 89
        assert b.pivot == 150.7
        assert b.duration_days == 20

    def test_bo_base_duration_bounds(self):
        """5-40d bases valid; model itself does not constrain duration."""
        b = BoBase(
            start_idx=0, end_idx=59, base_high=100.0, base_low=90.0,
            depth_pct=10.0, duration_days=60, pivot=99.0, vci=0.5,
            dryup_ratio=0.5,
        )
        assert b.duration_days == 60


class TestBoSetupRating:
    def test_bo_setup_rating_textbook(self):
        r = BoSetupRating(
            symbol="AAPL",
            exchange="NASDAQ",
            variant="classic",
            rating=5,
            label="textbook",
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
            volume_surge=True,
            surge_pct=320.0,
            extension=False,
            extension_pct=0.0,
            pivot=150.7,
            breakout_idx=94,
            breakout_date=date(2024, 5, 10),
            rvol10=2.5,
            as_of=date.today(),
        )
        assert r.rating == 5
        assert r.label == "textbook"
        assert r.variant == "classic"
        assert r.volume_surge is True

    def test_bo_setup_rating_lower_base_capped(self):
        """lower_base never reaches 5★ in the model contract."""
        r = BoSetupRating(
            symbol="XYZ",
            exchange="NYSE",
            variant="lower_base",
            rating=4,
            label="strong",
            prior_impulse=True,
            adr20=True,
            adr20_pct=7.0,
            base_duration=True,
            base_duration_days=18,
            vci=True,
            vci_ratio=0.5,
            ma_stack=True,
            surfing_dist_pct=1.0,
            pivot_kde=True,
            higher_lows=True,
            higher_lows_count=2,
            volume_surge=True,
            surge_pct=180.0,
            extension=False,
            extension_pct=0.0,
        )
        assert r.rating == 4
        assert r.variant == "lower_base"

    def test_bo_setup_rating_invalid_rating(self):
        with pytest.raises(ValidationError):
            BoSetupRating(
                symbol="A",
                exchange="NASDAQ",
                rating=2,  # BO ratings are only 3/4/5
                label="sub_standard",
                prior_impulse=False,
                adr20=False,
                base_duration=False,
                vci=False,
                ma_stack=False,
                pivot_kde=False,
                higher_lows=False,
                volume_surge=False,
                extension=False,
            )

    def test_bo_setup_rating_invalid_variant(self):
        with pytest.raises(ValidationError):
            BoSetupRating(
                symbol="A",
                exchange="NASDAQ",
                variant="breakaway",  # only classic / lower_base / none
                rating=3,
                label="sub_standard",
                prior_impulse=False,
                adr20=False,
                base_duration=False,
                vci=False,
                ma_stack=False,
                pivot_kde=False,
                higher_lows=False,
                volume_surge=False,
                extension=False,
            )


class TestBoScanBucket:
    def test_bo_scan_bucket_counts_match(self):
        ratings = [
            BoSetupRating(
                symbol=s, exchange="NASDAQ", variant="classic",
                rating=stars, label="textbook" if stars == 5 else "strong",
                prior_impulse=True, adr20=True, base_duration=True,
                vci=True, ma_stack=True, pivot_kde=True,
                higher_lows=True, volume_surge=True, extension=False,
            )
            for s, stars in [("A", 5), ("B", 4), ("C", 4), ("D", 3)]
        ]
        bucket = BoScanBucket(
            ratings=ratings,
            five_star=[r for r in ratings if r.rating == 5],
            four_star=[r for r in ratings if r.rating == 4],
            three_star=[r for r in ratings if r.rating <= 3],
            count=len(ratings),
            counts={"5": 1, "4": 2, "3": 1},
        )
        assert bucket.count == 4
        assert bucket.counts["5"] == 1
        assert bucket.counts["4"] == 2
        assert bucket.counts["3"] == 1

    def test_bo_scan_bucket_empty(self):
        bucket = BoScanBucket()
        assert bucket.count == 0
        assert bucket.counts["5"] == 0
        assert bucket.model_dump(mode="json") is not None


class TestBoRatedStock:
    def test_bo_rated_stock_merges_fields(self):
        r = BoRatedStock(
            symbol="AAPL",
            exchange="NASDAQ",
            company_name="Apple Inc.",
            setup_rating=5,
            setup_label="textbook",
            variant="classic",
            as_of=date.today(),
            sector="Technology",
            industry="Consumer Electronics",
            industry_group_strength_flag="HOT_SECTOR",
            is_category_leader=True,
            final_rating=5,
            final_label="textbook",
        )
        assert r.setup_rating == 5
        assert r.final_rating == 5
        assert r.variant == "classic"
        assert r.cap_applied is False

    def test_bo_rated_stock_lower_base(self):
        r = BoRatedStock(
            symbol="XYZ",
            exchange="NYSE",
            setup_rating=4,
            setup_label="strong",
            variant="lower_base",
            as_of=date.today(),
            final_rating=4,
            final_label="strong",
        )
        assert r.variant == "lower_base"
        assert r.final_rating == 4


class TestBoBuckets:
    def test_bo_rated_bucket_empty(self):
        bucket = BoRatedBucket()
        assert bucket.count == 0
        assert bucket.stocks == []

    def test_bo_enriched_bucket(self):
        bucket = BoEnrichedBucket(count=0)
        assert bucket.model_dump(mode="json")["count"] == 0


class TestBoNearMiss:
    def test_bo_near_miss_valid(self):
        nm = BoNearMiss(
            symbol="TEST",
            exchange="NYSE",
            variant="classic",
            rating=3,
            passed_essentials=["prior_impulse", "adr20", "base_duration", "vci",
                               "ma_stack", "pivot_kde", "higher_lows", "dryup"],
            failed_essentials=["volume_surge"],
            passed_count=8,
            failed_count=1,
            dryup_ratio=0.4,
            surge_pct=120.0,
            surfing_dist_pct=2.0,
            pivot=150.0,
            rvol10=2.5,
            rs_rating=85.0,
        )
        assert nm.symbol == "TEST"
        assert nm.rating == 3
        assert nm.passed_count == 8
        assert nm.failed_count == 1
        assert nm.failed_essentials == ["volume_surge"]

    def test_bo_near_miss_defaults(self):
        nm = BoNearMiss(symbol="A", exchange="NASDAQ")
        assert nm.variant == "none"
        assert nm.passed_essentials == []
        assert nm.failed_essentials == []
        assert nm.passed_count == 0
        assert nm.failed_count == 0
        assert nm.rs_rating is None

    def test_bo_near_miss_rating_literal(self):
        with pytest.raises(ValidationError):
            BoNearMiss(symbol="A", exchange="NASDAQ", rating=4)  # only 3 allowed
