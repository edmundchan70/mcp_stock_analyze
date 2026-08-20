"""Checkpoint plumbing tests: search agents honor the per-symbol checkpoint."""

from __future__ import annotations

import pytest

import stock_analyze.agents.catalyst as catalyst_mod
import stock_analyze.agents.enrichment as enrichment_mod
import stock_analyze.agents.rating as rating_mod
from stock_analyze.tools.builtins import _search_callable
from stock_analyze.tools.control import RunCancelled, register_control, unregister_control


def _raise_checkpoint():
    raise RunCancelled()


def test_catalyst_checkpoint_raises_cancelled():
    with pytest.raises(RunCancelled):
        catalyst_mod.enrich_with_catalysts(
            [{"symbol": "AAPL", "exchange": "NASDAQ"}],
            search_news=lambda s: [],
            summarize_catalyst=lambda s, snips: {
                "ticker": s,
                "catalyst_found": False,
                "catalyst_type": "UNKNOWN",
                "summary": "",
            },
            checkpoint=_raise_checkpoint,
        )


def test_rating_checkpoint_raises_cancelled():
    with pytest.raises(RunCancelled):
        rating_mod.rate_ep_catalysts(
            [{"symbol": "AAPL", "exchange": "NASDAQ"}],
            search_news=lambda s: [],
            rate_catalyst=lambda s, stock, snips: {
                "ticker": s,
                "ep_rating": 4,
                "ep_rationale": "ok",
            },
            checkpoint=_raise_checkpoint,
        )


def test_vcp_enrichment_checkpoint_raises_cancelled():
    with pytest.raises(RunCancelled):
        enrichment_mod.enrich_with_vcp_context(
            [{"symbol": "AAPL", "exchange": "NASDAQ"}],
            search_taxonomy=lambda s, c: [],
            search_leadership=lambda s, c: [],
            parse_context=lambda s, e, c, snips: {"symbol": s, "exchange": e},
            checkpoint=_raise_checkpoint,
        )


def test_search_callable_plumbs_checkpoint_to_all_agents(monkeypatch):
    calls: list[int] = []

    class FakeControl:
        def checkpoint(self) -> None:
            calls.append(1)

    cid = register_control(FakeControl())
    captured: dict[str, object] = {}

    def vcp_enrich(rows, checkpoint=None, on_ticker=None):
        captured["vcp"] = checkpoint
        return [{"symbol": r["symbol"], "exchange": r.get("exchange", "NASDAQ"), "sector": "Tech"} for r in rows]

    def catalyst_enrich(rows, checkpoint=None, on_ticker=None):
        captured["catalyst"] = checkpoint
        return [dict(r) for r in rows]

    def ep_rate(rows, checkpoint=None, on_ticker=None):
        captured["rating"] = checkpoint
        return [{**r, "ep_rating": 4, "catalyst_type": "EARNINGS"} for r in rows]

    monkeypatch.setattr(enrichment_mod, "enrich_with_vcp_context", vcp_enrich)
    monkeypatch.setattr(catalyst_mod, "enrich_with_catalysts", catalyst_enrich)
    monkeypatch.setattr(rating_mod, "rate_ep_catalysts", ep_rate)

    try:
        rows = [
            {"symbol": "AAPL", "exchange": "NASDAQ", "funnel_stars": 4},
            {"symbol": "NVDA", "exchange": "NASDAQ"},
        ]
        _search_callable({"in": rows}, {"__control_id__": cid})

        assert captured["vcp"] is not None
        assert captured["catalyst"] is not None
        assert captured["rating"] is not None
        captured["vcp"]()  # type: ignore[misc]
        captured["catalyst"]()  # type: ignore[misc]
        captured["rating"]()  # type: ignore[misc]
        assert calls == [1, 1, 1]
    finally:
        unregister_control(cid)
