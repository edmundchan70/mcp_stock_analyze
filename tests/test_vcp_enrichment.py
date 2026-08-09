"""Unit tests for VCP enrichment agent (mocked Tavily/LLM)."""

import pytest
from unittest.mock import MagicMock, patch
from stock_analyze.agents.enrichment import (
    enrich_with_vcp_context,
    load_vcp_stocks_from_input,
    _dedup_urls,
)
from stock_analyze.models.vcp import VcpContextEnrichment, VcpStructuralRating


def _make_structural() -> VcpStructuralRating:
    from datetime import date
    return VcpStructuralRating(
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


def _mock_taxonomy_search(symbol: str, company_name: str) -> list[dict[str, str]]:
    return [
        {"title": "AAPL Sector Analysis", "content": "Apple is in Tech", "url": "http://a.com/1"},
    ]


def _mock_leadership_search(symbol: str, company_name: str) -> list[dict[str, str]]:
    return [
        {"title": "AAPL Market Leader", "content": "Apple leads smartphones", "url": "http://b.com/1"},
    ]


def _mock_parser(symbol: str, company_name: str, snippets: list[dict[str, str]]) -> dict:
    return VcpContextEnrichment(
        symbol=symbol,
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        industry_group_strength_flag="HOT_SECTOR",
        is_category_leader=True,
        top_competitors=["MSFT", "GOOGL"],
        market_leadership_context="Top player",
        growth_catalysts="AI, Services",
        thematic_momentum="AI wave",
    ).model_dump()


class TestEnrichment:
    def test_enrichment_produces_context(self):
        """Enrichment with mocked Tavily/LLM produces valid context."""
        stocks = [_make_structural()]
        results = enrich_with_vcp_context(
            stocks,
            search_taxonomy=_mock_taxonomy_search,
            search_leadership=_mock_leadership_search,
            parse_context=_mock_parser,
        )
        assert len(results) == 1
        assert results[0].symbol == "AAPL"
        assert results[0].sector == "Technology"
        assert results[0].is_category_leader is True

    def test_soft_fail_on_tavily_error(self):
        """Tavily raises → stock gets error enrichment, not crash."""
        def failing_search(symbol, company_name):
            raise RuntimeError("Tavily down")
        stocks = [_make_structural()]
        results = enrich_with_vcp_context(
            stocks,
            search_taxonomy=failing_search,
            search_leadership=failing_search,
            parse_context=_mock_parser,
        )
        assert len(results) == 1
        assert results[0].error is not None

    def test_enrichment_max_concurrent(self):
        """Multiple stocks process with semaphore."""
        stocks = [_make_structural(), _make_structural()]
        stocks[1].symbol = "MSFT"
        results = enrich_with_vcp_context(
            stocks,
            search_taxonomy=_mock_taxonomy_search,
            search_leadership=_mock_leadership_search,
            parse_context=_mock_parser,
            max_concurrent=2,
        )
        assert len(results) == 2


class TestDedup:
    def test_dedup_urls_across_queries(self):
        a = [{"title": "T1", "content": "c1", "url": "http://x.com/a"}]
        b = [{"title": "T2", "content": "c2", "url": "http://x.com/a"}]
        merged = _dedup_urls(a, b)
        assert len(merged) == 1

    def test_dedup_keeps_unique(self):
        a = [{"title": "T1", "content": "c1", "url": "http://x.com/a"}]
        b = [{"title": "T2", "content": "c2", "url": "http://x.com/b"}]
        merged = _dedup_urls(a, b)
        assert len(merged) == 2


class TestLoadVcpStocks:
    def test_load_from_bare_list(self):
        stocks = load_vcp_stocks_from_input([{"symbol": "AAPL", "exchange": "NASDAQ"}])
        assert len(stocks) == 1

    def test_load_from_rated_bucket(self):
        stocks = load_vcp_stocks_from_input({
            "count": 2,
            "stocks": [
                {"symbol": "AAPL", "exchange": "NASDAQ"},
                {"symbol": "MSFT", "exchange": "NASDAQ"},
            ],
        })
        assert len(stocks) == 2

    def test_load_from_scan_bucket(self):
        stocks = load_vcp_stocks_from_input({
            "five_star": [{"symbol": "AAPL", "exchange": "NASDAQ"}],
            "four_star": [{"symbol": "MSFT", "exchange": "NASDAQ"}],
            "three_star": [{"symbol": "XYZ", "exchange": "NYSE"}],
        })
        # Only 5★ + 4★ pass to enrichment
        assert len(stocks) == 2

    def test_load_duplicate_dedup(self):
        """Duplicate symbols across buckets → only one copy."""
        stocks = load_vcp_stocks_from_input({
            "five_star": [{"symbol": "AAPL", "exchange": "NASDAQ"}],
            "four_star": [{"symbol": "AAPL", "exchange": "NASDAQ"}],
        })
        assert len(stocks) == 1
