"""Unit tests for VCP enrichment agent (mocked Tavily/LLM)."""

import json

import pytest
from unittest.mock import MagicMock, patch
from stock_analyze.agents.enrichment import (
    enrich_with_vcp_context,
    load_vcp_stocks_from_input,
    _dedup_urls,
    _is_transient_llm_error,
    _parse_llm_json,
    _with_retry,
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


def _mock_parser(
    symbol: str, exchange: str, company_name: str, snippets: list[dict[str, str]]
) -> dict:
    return VcpContextEnrichment(
        symbol=symbol,
        exchange=exchange,
        sector="Technology",
        industry="Consumer Electronics",
        industry_group_strength_flag="HOT_SECTOR",
        is_category_leader=True,
        top_competitors=["MSFT", "GOOGL"],
        market_leadership_context="Top player",
        growth_catalysts="AI, Services",
        thematic_momentum="AI wave",
    ).model_dump()


def _mock_parser_missing_exchange(
    symbol: str, exchange: str, company_name: str, snippets: list[dict[str, str]]
) -> dict:
    """Simulate the LLM bug: JSON omits the required `exchange` field."""
    return {
        "symbol": symbol,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "industry_group_strength_flag": "HOT_SECTOR",
        "is_category_leader": True,
        "top_competitors": ["MSFT", "GOOGL"],
        "market_leadership_context": "Top player",
        "growth_catalysts": "AI, Services",
        "thematic_momentum": "AI wave",
    }


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

    def test_enrichment_injects_exchange_when_llm_omits_it(self):
        """LLM JSON missing `exchange` → exchange injected from stock, no soft-fail."""
        stocks = [_make_structural()]
        results = enrich_with_vcp_context(
            stocks,
            search_taxonomy=_mock_taxonomy_search,
            search_leadership=_mock_leadership_search,
            parse_context=_mock_parser_missing_exchange,
        )
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].symbol == "AAPL"
        assert results[0].exchange == "NASDAQ"
        assert results[0].sector == "Technology"


class TestParseLlmJson:
    def test_parse_llm_json_injects_exchange(self):
        """LLM JSON without `exchange` validates after the field is injected."""
        content = json.dumps({
            "symbol": "TECK",
            "sector": "Materials",
            "industry_group_strength_flag": "NEUTRAL",
            "is_category_leader": False,
        })
        result = _parse_llm_json(content, symbol="TECK", exchange="NYSE")
        assert result["symbol"] == "TECK"
        assert result["exchange"] == "NYSE"
        assert result["sector"] == "Materials"

    def test_parse_llm_json_keeps_llm_exchange_when_present(self):
        """LLM-provided `exchange` is preserved over the injected default."""
        content = json.dumps({"symbol": "AAPL", "exchange": "NASDAQ"})
        result = _parse_llm_json(content, symbol="AAPL", exchange="NYSE")
        assert result["exchange"] == "NASDAQ"

    def test_parse_llm_json_raises_on_non_json(self):
        with pytest.raises(ValueError, match="non-JSON"):
            _parse_llm_json("not json at all", symbol="AAPL", exchange="NASDAQ")


class TestRetryPolicy:
    def test_with_retry_fails_fast_on_missing_field(self):
        """Deterministic missing-field error → no wasted retry LLM call."""
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise ValueError(
                "LLM JSON failed schema: 1 validation error for "
                "VcpContextEnrichment\nexchange\n  Field required [type=missing, ...]"
            )

        with pytest.raises(RuntimeError, match="LLM parse error"):
            _with_retry(boom, label="LLM parse", should_retry=_is_transient_llm_error)
        assert calls["n"] == 1

    def test_with_retry_regenerates_on_transient_error(self):
        """Malformed JSON may be a transient glitch → retried once."""
        calls = {"n": 0}

        def glitch():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("LLM returned non-JSON: ```json {...")
            return {"symbol": "AAPL", "exchange": "NASDAQ"}

        result = _with_retry(glitch, label="LLM parse", should_retry=_is_transient_llm_error)
        assert calls["n"] == 2
        assert result == {"symbol": "AAPL", "exchange": "NASDAQ"}


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
