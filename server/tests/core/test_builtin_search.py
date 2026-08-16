"""BO/EP routing in the AI Search callable (Q6).

BO rows carry ``funnel_stars`` (no ``structural_rating``) and must route to the
VCP/BO enrichment path, not the EP catalyst path. EP rows (neither field) keep
the catalyst + rating chain.
"""

from __future__ import annotations

import stock_analyze.agents.catalyst as catalyst_mod
import stock_analyze.agents.enrichment as enrichment_mod
import stock_analyze.agents.rating as rating_mod
from stock_analyze.tools.builtins import _search_callable


def _vcp_enrich(rows):
    # Real enrich_with_vcp_context returns one context object per row.
    return [
        {"symbol": r["symbol"], "exchange": r.get("exchange", "NASDAQ"), "sector": "Tech"}
        for r in rows
    ]


def _catalyst_enrich(rows):
    return [dict(r) for r in rows]


def _ep_rate(rows):
    return [{**r, "ep_rating": 4, "catalyst_type": "EARNINGS"} for r in rows]


def _patch_agents(monkeypatch):
    monkeypatch.setattr(enrichment_mod, "enrich_with_vcp_context", _vcp_enrich)
    monkeypatch.setattr(catalyst_mod, "enrich_with_catalysts", _catalyst_enrich)
    monkeypatch.setattr(rating_mod, "rate_ep_catalysts", _ep_rate)


def test_bo_rows_route_to_vcp_enrichment(monkeypatch):
    _patch_agents(monkeypatch)
    rows = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "funnel_stars": 4},  # BO shape
        {"symbol": "MSFT", "exchange": "NASDAQ", "structural_rating": 5},  # VCP shape
    ]
    out = _search_callable({"in": rows}, {})
    by_symbol = {r["symbol"]: r for r in out}
    # both structural lanes go through the VCP/BO enrichment path
    assert by_symbol["AAPL"]["enrichment"]["sector"] == "Tech"
    assert by_symbol["MSFT"]["enrichment"]["sector"] == "Tech"
    assert "ep_rating" not in by_symbol["AAPL"]
    assert "ep_rating" not in by_symbol["MSFT"]


def test_ep_rows_route_to_catalyst_path(monkeypatch):
    _patch_agents(monkeypatch)
    rows = [{"symbol": "NVDA", "exchange": "NASDAQ"}]  # no structural fields
    out = _search_callable({"in": rows}, {})
    assert out[0]["ep_rating"] == 4
    assert out[0]["catalyst_type"] == "EARNINGS"
    assert "enrichment" not in out[0]
