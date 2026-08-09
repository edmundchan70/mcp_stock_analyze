"""Unit tests for VCP gate predicates and down-only cap logic."""

import pytest
from datetime import date
from unittest.mock import MagicMock
from stock_analyze.models.vcp import (
    VcpContextEnrichment,
    VcpStructuralRating,
    VcpRatedStock,
)
from stock_analyze.scanners.vcp.gates import (
    passes_stage2_gate,
    passes_vcp_gate,
    apply_vcp_caps,
    build_rated_stock,
)


def _make_rating(
    symbol: str = "AAPL",
    exchange: str = "NASDAQ",
    structural_rating: int = 5,
    stage2: bool = True,
    rs_rating: float = 85.0,
    **kwargs,
) -> VcpStructuralRating:
    defaults = dict(
        symbol=symbol,
        exchange=exchange,
        structural_rating=structural_rating,
        structural_label="textbook" if structural_rating >= 5 else "strong",
        stage2_trend=stage2,
        rs_rating=rs_rating,
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
    defaults.update(kwargs)
    return VcpStructuralRating(**defaults)


def _make_context(
    symbol: str = "AAPL",
    exchange: str = "NASDAQ",
    flag: str = "NEUTRAL",
    is_leader: bool = True,
) -> VcpContextEnrichment:
    return VcpContextEnrichment(
        symbol=symbol,
        exchange=exchange,
        sector="Technology",
        industry="Consumer Electronics",
        industry_group_strength_flag=flag,
        is_category_leader=is_leader,
        top_competitors=["MSFT", "GOOGL"],
        market_leadership_context="Top player in smartphones",
        growth_catalysts="AI, Services growth",
        thematic_momentum="AI wave",
    )


# ── Stage 2 Gate ──────────────────────────────────────────────────


class TestStage2Gate:
    def test_stage2_gate_rejects_rs_below_70(self):
        r = _make_rating(stage2=True, rs_rating=69.9)
        assert not passes_stage2_gate(r)

    def test_stage2_gate_rejects_non_stage2(self):
        r = _make_rating(stage2=False, rs_rating=85.0)
        assert not passes_stage2_gate(r)

    def test_stage2_gate_rejects_both_bad(self):
        r = _make_rating(stage2=False, rs_rating=60.0)
        assert not passes_stage2_gate(r)

    def test_stage2_gate_passes_rs_85_stage2(self):
        r = _make_rating(stage2=True, rs_rating=85.0)
        assert passes_stage2_gate(r)

    def test_stage2_gate_passes_rs_70_exactly(self):
        r = _make_rating(stage2=True, rs_rating=70.0)
        assert passes_stage2_gate(r)


# ── VCP Structural Gate ───────────────────────────────────────────


class TestVcpGate:
    def test_vcp_gate_passes_5star(self):
        r = _make_rating(structural_rating=5)
        assert passes_vcp_gate(r)

    def test_vcp_gate_passes_4star(self):
        r = _make_rating(structural_rating=4)
        assert passes_vcp_gate(r)

    def test_vcp_gate_rejects_3star(self):
        r = _make_rating(structural_rating=3)
        assert not passes_vcp_gate(r)

    def test_vcp_gate_rejects_2star(self):
        r = _make_rating(structural_rating=2)
        assert not passes_vcp_gate(r)

    def test_vcp_gate_rejects_1star(self):
        r = _make_rating(structural_rating=1)
        assert not passes_vcp_gate(r)


# ── Down-Only Caps ────────────────────────────────────────────────


class TestDownOnlyCaps:
    def test_cap_5star_leader_hot_sector(self):
        """5★ + leader + HOT_SECTOR → 5★ (no cap)."""
        ctx = _make_context(flag="HOT_SECTOR", is_leader=True)
        final, capped, reason = apply_vcp_caps(5, ctx)
        assert final == 5
        assert not capped

    def test_cap_5star_leader_neutral(self):
        """5★ + leader + NEUTRAL → 5★ (no cap)."""
        ctx = _make_context(flag="NEUTRAL", is_leader=True)
        final, capped, reason = apply_vcp_caps(5, ctx)
        assert final == 5
        assert not capped

    def test_cap_5star_non_leader(self):
        """5★ + non-leader → 4★ (cap)."""
        ctx = _make_context(flag="HOT_SECTOR", is_leader=False)
        final, capped, reason = apply_vcp_caps(5, ctx)
        assert final == 4
        assert capped

    def test_cap_5star_declining_group(self):
        """5★ + leader + DECLINING_GROUP → 4★ (cap)."""
        ctx = _make_context(flag="DECLINING_GROUP", is_leader=True)
        final, capped, reason = apply_vcp_caps(5, ctx)
        assert final == 4
        assert capped

    def test_cap_4star_declining_group(self):
        """4★ + DECLINING_GROUP → 3★ (cap)."""
        ctx = _make_context(flag="DECLINING_GROUP", is_leader=True)
        final, capped, reason = apply_vcp_caps(4, ctx)
        assert final == 3
        assert capped

    def test_cap_4star_hot_or_neutral(self):
        """4★ + HOT/NEUTRAL → 4★ (no cap)."""
        ctx = _make_context(flag="HOT_SECTOR", is_leader=False)
        final, capped, reason = apply_vcp_caps(4, ctx)
        assert final == 4
        assert not capped

    def test_cap_3star_any_context(self):
        """3★ + any context → 3★ (never boosted)."""
        ctx = _make_context(flag="HOT_SECTOR", is_leader=True)
        final, capped, reason = apply_vcp_caps(3, ctx)
        assert final == 3
        assert not capped

    def test_cap_never_boosts(self):
        """3★ + leader + HOT_SECTOR → 3★ (never 4★)."""
        ctx = _make_context(flag="HOT_SECTOR", is_leader=True)
        final, capped, reason = apply_vcp_caps(3, ctx)
        assert final == 3

    def test_build_rated_stock_preserves_fields(self):
        """build_rated_stock merges all fields correctly."""
        rating = _make_rating(structural_rating=5)
        ctx = _make_context(flag="HOT_SECTOR", is_leader=True)
        rated = build_rated_stock(rating, ctx)
        assert rated.symbol == "AAPL"
        assert rated.structural_rating == 5
        assert rated.final_rating == 5
        assert rated.sector == "Technology"
        assert rated.is_category_leader is True
        assert rated.cap_applied is False
