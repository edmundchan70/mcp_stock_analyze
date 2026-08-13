"""Unit tests for BO gate predicates, ADR envelope, and rated-stock builder."""

import pytest
from datetime import date

import pandas as pd

from bo_fixtures import make_scenario

from stock_analyze.models.bo import BoSetupRating
from stock_analyze.models.vcp import VcpContextEnrichment
from stock_analyze.scanners.bo.gates import (
    build_bo_rated_stock,
    passes_adr_envelope,
    passes_bo_gate,
    passes_market_cap_gate,
)
from stock_analyze.scanners.vcp.gates import compute_adv_dollar, passes_liquidity_gate


def _make_rating(rating: int = 4, variant: str = "classic", **kwargs) -> BoSetupRating:
    defaults = dict(
        symbol="AAPL",
        exchange="NASDAQ",
        variant=variant,
        rating=rating,
        label="strong" if rating == 4 else "textbook",
        prior_impulse=True,
        adr20=True,
        base_duration=True,
        vci=True,
        ma_stack=True,
        pivot_kde=True,
        higher_lows=True,
        dryup=True,
        volume_surge=True,
        extension=False,
        as_of=date.today(),
    )
    defaults.update(kwargs)
    return BoSetupRating(**defaults)


def _make_context(
    flag: str = "NEUTRAL",
    is_leader: bool = True,
    symbol: str = "AAPL",
) -> VcpContextEnrichment:
    return VcpContextEnrichment(
        symbol=symbol,
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        industry_group_strength_flag=flag,
        is_category_leader=is_leader,
        top_competitors=["MSFT", "GOOGL"],
        market_leadership_context="Top player in smartphones",
        growth_catalysts="AI, Services growth",
        thematic_momentum="AI wave",
    )


# ── ADR20 envelope ───────────────────────────────────────────────────


class TestAdrEnvelope:
    def test_passes_mid_range(self):
        assert passes_adr_envelope(6.0) is True

    def test_rejects_below_4(self):
        assert passes_adr_envelope(3.99) is False

    def test_rejects_above_12(self):
        assert passes_adr_envelope(12.01) is False

    def test_measured_high_adr_scenario_fails(self):
        df = make_scenario("high_adr")
        from stock_analyze.scanners.bo.metrics import avg_daily_range_pct

        assert passes_adr_envelope(avg_daily_range_pct(df)) is False


# ── BO gate (rating >= 4 survives to enrichment) ─────────────────────


class TestBoGate:
    def test_five_star_passes(self):
        assert passes_bo_gate(_make_rating(5)) is True

    def test_four_star_passes(self):
        assert passes_bo_gate(_make_rating(4)) is True

    def test_three_star_rejected(self):
        assert passes_bo_gate(_make_rating(3)) is False


# ── Liquidity gate (reused from VCP gates) ───────────────────────────


class TestLiquidityGate:
    def test_high_dollar_volume_passes(self):
        n = 70
        closes = [100.0] * n
        volumes = [1_000_000.0] * n  # ADV$ = 100 × 1M = $100M
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [101.0] * n,
                "low": [99.0] * n,
                "close": closes,
                "volume": volumes,
            },
            index=idx,
        )
        assert compute_adv_dollar(df) == pytest.approx(100_000_000.0)
        assert passes_liquidity_gate(df) is True

    def test_low_dollar_volume_rejected(self):
        n = 70
        closes = [10.0] * n
        volumes = [100_000.0] * n  # ADV$ = 10 × 100k = $1M
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [10.5] * n,
                "low": [9.5] * n,
                "close": closes,
                "volume": volumes,
            },
            index=idx,
        )
        assert passes_liquidity_gate(df) is False


# ── lower_base ceiling ───────────────────────────────────────────────


class TestLowerBaseCeiling:
    def test_lower_base_never_rates_five(self):
        r = make_scenario("lower_base")
        from stock_analyze.scanners.bo.metrics import score_bo_setup

        rating = score_bo_setup(r, symbol="TEST", exchange="NYSE")
        assert rating is not None
        assert rating.variant == "lower_base"
        assert rating.rating <= 4


# ── build_bo_rated_stock + down-only caps ────────────────────────────


class TestBuildBoRatedStock:
    def test_merges_setup_and_context(self):
        setup = _make_rating(5, symbol="AAPL", exchange="NASDAQ")
        ctx = _make_context(is_leader=True, flag="HOT_SECTOR")
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.symbol == "AAPL"
        assert stock.sector == "Technology"
        assert stock.is_category_leader is True
        assert stock.final_rating == 5
        assert stock.final_label == "textbook"
        assert stock.cap_applied is False

    def test_five_star_capped_when_not_leader(self):
        setup = _make_rating(5, symbol="AAPL")
        ctx = _make_context(is_leader=False)
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.final_rating == 4
        assert stock.cap_applied is True
        assert "non-leader" in stock.cap_reason

    def test_four_star_capped_by_declining_group(self):
        setup = _make_rating(4, symbol="AAPL")
        ctx = _make_context(flag="DECLINING_GROUP", is_leader=True)
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.final_rating == 3
        assert stock.cap_applied is True

    def test_four_star_no_cap_neutral(self):
        setup = _make_rating(4, symbol="AAPL")
        ctx = _make_context(flag="NEUTRAL", is_leader=True)
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.final_rating == 4
        assert stock.cap_applied is False

    def test_three_star_never_capped(self):
        setup = _make_rating(3, symbol="AAPL")
        ctx = _make_context(flag="DECLINING_GROUP", is_leader=False)
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.final_rating == 3
        assert stock.cap_applied is False

    def test_variant_and_setup_fields_preserved(self):
        setup = _make_rating(4, variant="lower_base", symbol="AAPL")
        ctx = _make_context()
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.variant == "lower_base"
        assert stock.setup_rating == 4
        assert stock.setup_label == "strong"

    def test_error_passthrough(self):
        setup = _make_rating(4, symbol="AAPL")
        ctx = _make_context()
        ctx.error = "Tavily down"
        stock = build_bo_rated_stock(setup, ctx)
        assert stock.error == "Tavily down"


# ── Market-Cap Gate (reused from VCP gates) ─────────────────────


class TestMarketCapGate:
    def test_passes_above_threshold(self):
        assert passes_market_cap_gate(500_000_000) is True

    def test_passes_at_threshold(self):
        assert passes_market_cap_gate(100_000_000) is True

    def test_rejects_below_threshold(self):
        assert passes_market_cap_gate(99_999_999) is False

    def test_rejects_none(self):
        assert passes_market_cap_gate(None) is False

    def test_rejects_zero(self):
        assert passes_market_cap_gate(0) is False
