"""Seam: parse_force_include_text (messy paste → SymbolKeys + rejected/errors)."""

from __future__ import annotations

from stock_analyze.force_include import ForceIncludeParseResult, parse_force_include_text


def test_parse_messy_paren_list_returns_symbols():
    def fake_parse(raw: str) -> dict:
        assert "JHX" in raw
        return {
            "symbols": [
                {"symbol": "JHX", "exchange": "NYSE"},
                {"symbol": "KGC"},
                {"symbol": "LUNR", "exchange": "NASDAQ"},
                {"symbol": "MB", "exchange": "NASDAQ"},
            ],
            "rejected": [],
        }

    result = parse_force_include_text("( JHX, KGC, LUNR, MB, )", parse_fn=fake_parse)

    assert result.symbols == [
        ("JHX", "NYSE"),
        ("KGC", "NASDAQ"),
        ("LUNR", "NASDAQ"),
        ("MB", "NASDAQ"),
    ]
    assert result.rejected == []
    assert result.errors == []


def test_parse_preserves_rejected_and_dedups():
    def fake_parse(raw: str) -> dict:
        return {
            "symbols": [
                {"symbol": "aapl", "exchange": "nasdaq"},
                {"symbol": "AAPL", "exchange": "NASDAQ"},
                {"symbol": "", "exchange": "NYSE"},
            ],
            "rejected": ["???", "not a ticker"],
        }

    result = parse_force_include_text("AAPL ??? AAPL not a ticker", parse_fn=fake_parse)

    assert result.symbols == [("AAPL", "NASDAQ")]
    assert result.rejected == ["???", "not a ticker"]
    assert result.errors == []


def test_parse_empty_raw_returns_empty_without_calling_llm():
    called = {"n": 0}

    def fake_parse(raw: str) -> dict:
        called["n"] += 1
        return {"symbols": [], "rejected": []}

    result = parse_force_include_text("   \n  ", parse_fn=fake_parse)

    assert result == ForceIncludeParseResult(symbols=[], rejected=[], errors=[])
    assert called["n"] == 0


def test_parse_records_errors_when_parse_fn_raises():
    def boom(raw: str) -> dict:
        raise ValueError("OPENROUTER_API_KEY is required")

    result = parse_force_include_text("JHX, KGC", parse_fn=boom)

    assert result.symbols == []
    assert result.rejected == []
    assert any("OPENROUTER_API_KEY" in e for e in result.errors)
