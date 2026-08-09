"""Seams: enrich_with_catalysts, load_stocks_from_input."""

import json
from datetime import date

import pytest

from stock_analyze.agents.catalyst import enrich_with_catalysts, load_stocks_from_input


def _stock(**overrides):
    base = {
        "symbol": "NVDA",
        "exchange": "NASDAQ",
        "price": 125.0,
        "market_cap": 3_000_000_000.0,
        "avg_dollar_volume_50d": 50_000_000.0,
        "gap_pct": 11.2,
        "rvol10": 4.5,
        "event_dollar_volume": 150_000_000.0,
        "force_included": False,
        "as_of": date(2026, 8, 8),
    }
    base.update(overrides)
    return base


def test_enrich_passthrough_and_catalyst_fields():
    def search_news(symbol: str):
        assert symbol == "NVDA"
        return [{"title": "NVDA beats", "content": "EPS +45% YoY, raises guidance"}]

    def summarize(symbol: str, snippets):
        assert snippets
        return {
            "ticker": symbol,
            "catalyst_found": True,
            "catalyst_type": "EARNINGS",
            "summary": "Q2 EPS +45% YoY. FY guidance raised 15%.",
        }

    out = enrich_with_catalysts(
        [_stock()],
        search_news=search_news,
        summarize_catalyst=summarize,
    )

    assert len(out) == 1
    row = out[0]
    assert row.symbol == "NVDA"
    assert row.price == 125.0
    assert row.rvol10 == 4.5
    assert row.event_dollar_volume == 150_000_000.0
    assert row.market_cap == 3_000_000_000.0
    assert row.catalyst_found is True
    assert row.catalyst_type == "EARNINGS"
    assert "EPS" in row.catalyst_summary


def test_enrich_no_clear_news_marks_unknown():
    out = enrich_with_catalysts(
        [_stock()],
        search_news=lambda s: [{"title": "Analyst chatter", "content": "No filings"}],
        summarize_catalyst=lambda s, snips: {
            "ticker": s,
            "catalyst_found": False,
            "catalyst_type": "UNKNOWN",
            "summary": "No clear catalyst found.",
        },
    )
    assert out[0].catalyst_found is False
    assert out[0].catalyst_type == "UNKNOWN"


def test_enrich_tavily_error_soft_fails_with_clear_summary():
    def boom(symbol: str):
        raise RuntimeError("rate limited")

    out = enrich_with_catalysts(
        [_stock()],
        search_news=boom,
        summarize_catalyst=lambda s, snips: pytest.fail("LLM should not run"),
    )
    assert out[0].catalyst_found is False
    assert out[0].catalyst_type == "UNKNOWN"
    assert "Tavily error" in out[0].catalyst_summary
    assert "rate limited" in out[0].catalyst_summary


def test_enrich_llm_error_retries_then_soft_fails():
    calls = {"n": 0}

    def flaky(symbol: str, snippets):
        calls["n"] += 1
        raise ValueError("bad json")

    out = enrich_with_catalysts(
        [_stock()],
        search_news=lambda s: [{"title": "t", "content": "c"}],
        summarize_catalyst=flaky,
    )
    assert calls["n"] == 2  # initial + 1 retry
    assert out[0].catalyst_found is False
    assert "LLM error" in out[0].catalyst_summary
    assert "bad json" in out[0].catalyst_summary


def test_load_stocks_from_input_defaults_to_strict_bucket():
    payload = {
        "baseline": {"count": 1, "stocks": [_stock(symbol="WEAK", gap_pct=5.0)]},
        "strict": {"count": 1, "stocks": [_stock(symbol="STRONG", gap_pct=11.0)]},
    }
    stocks = load_stocks_from_input(payload, select="strict")
    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "STRONG"


def test_load_stocks_from_input_bare_list():
    stocks = load_stocks_from_input([_stock()], select="strict")
    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "NVDA"


def test_load_stocks_from_input_both_empty_buckets_returns_empty_list():
    payload = {
        "baseline": {"count": 0, "stocks": []},
        "strict": {"count": 0, "stocks": []},
    }
    assert load_stocks_from_input(payload, select="both") == []


def test_cli_catalyst_selects_strict_and_writes_envelope(tmp_path, monkeypatch):
    from stock_analyze.models.catalyst import CatalystEnrichedStock
    from stock_analyze import cli as cli_mod

    in_path = tmp_path / "ep.json"
    out_path = tmp_path / "out.json"
    in_path.write_text(
        json.dumps(
            {
                "baseline": {"count": 1, "stocks": [_stock(symbol="WEAK")]},
                "strict": {"count": 1, "stocks": [_stock(symbol="STRONG")]},
            },
            default=str,
        ),
        encoding="utf-8",
    )

    def fake_enrich(stocks, **kwargs):
        assert len(stocks) == 1
        assert stocks[0]["symbol"] == "STRONG"
        base = dict(stocks[0])
        if isinstance(base.get("as_of"), str):
            base["as_of"] = date.fromisoformat(base["as_of"])
        return [
            CatalystEnrichedStock(
                **base,
                catalyst_found=True,
                catalyst_type="CONTRACT",
                catalyst_summary="Won $200M deal.",
            )
        ]

    import stock_analyze.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "enrich_with_catalysts", fake_enrich)
    monkeypatch.setattr(pipeline_mod, "load_dotenv", lambda: None)

    rc = cli_mod.main(["catalyst", "--in", str(in_path), "--out", str(out_path)])
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["stocks"][0]["symbol"] == "STRONG"
    assert payload["stocks"][0]["catalyst_type"] == "CONTRACT"
