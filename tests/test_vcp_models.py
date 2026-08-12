"""Tests for VCP Pydantic model validation."""

import pytest
from datetime import date
from pydantic import ValidationError

from stock_analyze.models.vcp import (
    VcpContraction,
    VcpContextEnrichment,
    VcpRatedStock,
    VcpScanBucket,
    VcpStructuralRating,
)


class TestVcpContraction:
    def test_vcp_contraction_valid(self):
        c = VcpContraction(
            index=0,
            high_pivot=100.0,
            low_pivot=90.0,
            dollar_range=10.0,
            depth_pct=10.0,
            avg_volume=500000.0,
            duration_days=15,
        )
        assert c.index == 0
        assert c.high_pivot == 100.0
        assert c.low_pivot == 90.0
        assert c.dollar_range == 10.0
        assert c.depth_pct == 10.0

    def test_vcp_contraction_max_depth(self):
        """Depth > 50% still valid (deep corrections exist)."""
        c = VcpContraction(
            index=0,
            high_pivot=100.0,
            low_pivot=30.0,
            dollar_range=70.0,
            depth_pct=70.0,
            avg_volume=200000.0,
            duration_days=30,
        )
        assert c.depth_pct == 70.0


class TestVcpStructuralRating:
    def test_vcp_structural_rating_range(self):
        r = VcpStructuralRating(
            symbol="AAPL",
            exchange="NASDAQ",
            structural_rating=5,
            structural_label="textbook",
            stage2_trend=True,
            rs_rating=85.0,
            proximity_52w_pct=95.0,
            contraction_count=3,
            trough_symmetry_score=5,
            peak_symmetry_score=5,
            dollar_range_score=5,
            depth_score=5,
            tight_closes_score=5,
            volume_decay_score=5,
            time_contraction_score=5,
            as_of=date.today(),
        )
        assert r.structural_rating == 5
        assert r.structural_label == "textbook"


class TestVcpContextEnrichment:
    def test_vcp_context_enrichment_required_fields(self):
        """All required fields validate."""
        c = VcpContextEnrichment(symbol="AAPL", exchange="NASDAQ")
        assert c.symbol == "AAPL"
        assert c.sector == "Unknown"
        assert c.industry_group_strength_flag == "NEUTRAL"

    def test_vcp_context_enrichment_strength_flag_enum(self):
        """Only valid strength flags accepted."""
        for valid in ("HOT_SECTOR", "NEUTRAL", "DECLINING_GROUP"):
            c = VcpContextEnrichment(
                symbol="AAPL",
                exchange="NASDAQ",
                industry_group_strength_flag=valid,
            )
            assert c.industry_group_strength_flag == valid

    def test_vcp_context_enrichment_invalid_flag(self):
        with pytest.raises(ValidationError):
            VcpContextEnrichment(
                symbol="AAPL",
                exchange="NASDAQ",
                industry_group_strength_flag="INVALID_FLAG",
            )


class TestVcpRatedStock:
    def test_vcp_rated_stock_merges_fields(self):
        r = VcpRatedStock(
            symbol="AAPL",
            exchange="NASDAQ",
            company_name="Apple Inc.",
            structural_rating=5,
            structural_label="textbook",
            as_of=date.today(),
            sector="Technology",
            industry="Consumer Electronics",
            industry_group_strength_flag="HOT_SECTOR",
            is_category_leader=True,
            market_leadership_context="Top 3 in smartphones",
            growth_catalysts="AI, services",
            thematic_momentum="AI wave",
            final_rating=5,
            final_label="textbook",
        )
        assert r.structural_rating == 5
        assert r.final_rating == 5
        assert r.is_category_leader is True
        assert r.cap_applied is False


class TestVcpScanBucket:
    def test_vcp_scan_bucket_counts_match(self):
        ratings = [
            VcpStructuralRating(
                symbol=s, exchange="NASDAQ", structural_rating=stars,
                structural_label="textbook" if stars == 5 else "strong",
                stage2_trend=True, rs_rating=85.0, proximity_52w_pct=95.0,
                contraction_count=3,
                trough_symmetry_score=stars, peak_symmetry_score=stars,
                dollar_range_score=stars, depth_score=stars,
                tight_closes_score=stars, volume_decay_score=stars,
                time_contraction_score=stars,
            )
            for s, stars in [("A", 5), ("B", 4), ("C", 4), ("D", 3)]
        ]
        bucket = VcpScanBucket(
            ratings=ratings,
            five_star=[r for r in ratings if r.structural_rating == 5],
            four_star=[r for r in ratings if r.structural_rating == 4],
            three_star=[r for r in ratings if r.structural_rating <= 3],
            count=len(ratings),
            counts={"5": 1, "4": 2, "3": 1},
        )
        assert bucket.count == 4
        assert bucket.counts["5"] == 1
        assert bucket.counts["4"] == 2
        assert bucket.counts["3"] == 1

    def test_vcp_scan_bucket_empty(self):
        bucket = VcpScanBucket()
        assert bucket.count == 0
        assert bucket.counts["5"] == 0
        assert bucket.counts["4"] == 0
        assert bucket.counts["3"] == 0
        assert bucket.model_dump(mode="json") is not None
