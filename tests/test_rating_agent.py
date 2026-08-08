"""Seams: rate_ep_catalysts, apply_rating_caps, rate CLI."""

import json
from datetime import date

import pytest

from stock_analyze.agents.rating import apply_rating_caps, rate_ep_catalysts
from stock_analyze.models.rating import RATING_LABELS


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
        "catalyst_found": True,
        "catalyst_type": "EARNINGS",
        "catalyst_summary": "Q2 EPS +45% YoY. FY guidance raised 15%.",
    }
    base.update(overrides)
    return base


def test_rate_passthrough_and_rating_fields():
    def search_news(symbol: str):
        assert symbol == "NVDA"
        return [{"title": "NVDA beats", "content": "EPS +45% YoY, raises guidance"}]

    def rate_fn(symbol: str, stock: dict, snippets: list):
        assert snippets
        assert stock["rvol10"] == 4.5
        return {
            "ticker": symbol,
            "ep_rating": 5,
            "ep_rationale": "Huge EPS beat and guidance raise with strong RVOL.",
        }

    out = rate_ep_catalysts(
        [_stock()],
        search_news=search_news,
        rate_catalyst=rate_fn,
    )

    assert len(out) == 1
    row = out[0]
    assert row.symbol == "NVDA"
    assert row.catalyst_type == "EARNINGS"
    assert row.ep_rating == 5
    assert row.ep_rating_label == "textbook"
    assert row.ep_catalyst_match is True
    assert "EPS" in row.ep_rationale


def test_clamp_unknown_max_2():
    assert apply_rating_caps(5, catalyst_found=False, catalyst_type="UNKNOWN", rvol10=10.0) == 2
    assert apply_rating_caps(5, catalyst_found=True, catalyst_type="UNKNOWN", rvol10=10.0) == 2


def test_clamp_pr_max_3():
    assert apply_rating_caps(5, catalyst_found=True, catalyst_type="PR", rvol10=10.0) == 3


def test_clamp_contract_fda_max_4():
    assert apply_rating_caps(5, catalyst_found=True, catalyst_type="CONTRACT", rvol10=10.0) == 4
    assert apply_rating_caps(5, catalyst_found=True, catalyst_type="FDA", rvol10=10.0) == 4


def test_clamp_low_rvol_max_4():
    assert apply_rating_caps(5, catalyst_found=True, catalyst_type="EARNINGS", rvol10=2.9) == 4


def test_rate_applies_clamps_after_llm():
    out = rate_ep_catalysts(
        [_stock(catalyst_type="CONTRACT", catalyst_summary="Big deal")],
        search_news=lambda s: [{"title": "t", "content": "c"}],
        rate_catalyst=lambda s, stock, snips: {
            "ticker": s,
            "ep_rating": 5,
            "ep_rationale": "Massive contract.",
        },
    )
    assert out[0].ep_rating == 4
    assert out[0].ep_rating_label == "acceptable"
    assert out[0].ep_catalyst_match is True


def test_rate_soft_fail_forces_1():
    def boom(symbol: str):
        raise RuntimeError("rate limited")

    out = rate_ep_catalysts(
        [_stock()],
        search_news=boom,
        rate_catalyst=lambda s, stock, snips: pytest.fail("LLM should not run"),
    )
    assert out[0].ep_rating == 1
    assert out[0].ep_rating_label == "bs"
    assert out[0].ep_catalyst_match is False
    assert "Tavily error" in out[0].ep_rationale
    assert "rate limited" in out[0].ep_rationale


def test_rate_llm_error_retries_then_soft_fails():
    calls = {"n": 0}

    def flaky(symbol: str, stock: dict, snippets):
        calls["n"] += 1
        raise ValueError("bad json")

    out = rate_ep_catalysts(
        [_stock()],
        search_news=lambda s: [{"title": "t", "content": "c"}],
        rate_catalyst=flaky,
    )
    assert calls["n"] == 2
    assert out[0].ep_rating == 1
    assert "LLM error" in out[0].ep_rationale


def test_rate_sorts_best_to_worst():
    def rate_fn(symbol: str, stock: dict, snippets):
        return {
            "ticker": symbol,
            "ep_rating": {"WEAK": 3, "MID": 4, "TOP": 5}[symbol],
            "ep_rationale": f"{symbol} rated",
        }

    out = rate_ep_catalysts(
        [
            _stock(symbol="WEAK", rvol10=5.0, catalyst_type="PR", catalyst_summary="PR"),
            _stock(symbol="TOP", rvol10=8.0),
            _stock(symbol="MID", rvol10=3.5, catalyst_type="GUIDANCE", catalyst_summary="Raise"),
        ],
        search_news=lambda s: [{"title": "t", "content": "c"}],
        rate_catalyst=rate_fn,
    )
    assert [r.symbol for r in out] == ["TOP", "MID", "WEAK"]
    assert out[0].ep_catalyst_match is True
    assert out[2].ep_catalyst_match is False


def test_rating_labels_map():
    assert RATING_LABELS[5] == "textbook"
    assert RATING_LABELS[1] == "bs"


def test_cli_rate_default_console_min_4_writes_full_json(tmp_path, monkeypatch, capsys):
    from stock_analyze.models.rating import EpRatedStock
    from stock_analyze import cli as cli_mod

    in_path = tmp_path / "cat.json"
    out_path = tmp_path / "rated.json"
    in_path.write_text(
        json.dumps({"count": 2, "stocks": [_stock(symbol="TOP"), _stock(symbol="LOW")]}, default=str),
        encoding="utf-8",
    )

    def fake_rate(stocks, **kwargs):
        rows = []
        for s in stocks:
            base = dict(s)
            if isinstance(base.get("as_of"), str):
                base["as_of"] = date.fromisoformat(base["as_of"])
            rating = 5 if base["symbol"] == "TOP" else 2
            rows.append(
                EpRatedStock(
                    **base,
                    ep_rating=rating,
                    ep_rating_label=RATING_LABELS[rating],
                    ep_rationale="test",
                    ep_catalyst_match=rating >= 4,
                )
            )
        return sorted(rows, key=lambda r: (-r.ep_rating, -r.rvol10))

    monkeypatch.setattr(cli_mod, "rate_ep_catalysts", fake_rate)
    monkeypatch.setattr(cli_mod, "load_dotenv", lambda: None)

    rc = cli_mod.main(["rate", "--in", str(in_path), "--out", str(out_path)])
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["count"] == 2
    assert {s["symbol"] for s in payload["stocks"]} == {"TOP", "LOW"}

    printed = capsys.readouterr().out
    assert "TOP" in printed
    assert "5★" in printed
    # Default console min-rating=4 hides LOW (2★); full JSON still has both
    table_part = printed.split("stars", 1)[-1]
    assert "LOW" not in table_part
