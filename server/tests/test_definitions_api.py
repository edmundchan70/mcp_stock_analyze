"""API tests for definitions, component templates, tools, preview + graph runs (T28)."""

from __future__ import annotations

import httpx
import pytest

from app.main import create_app
from fakes import FakeRepo

# Canvas-shaped graph: universe -> scanner -> report.
VALID_GRAPH = {
    "name": "vcp-lite",
    "nodes": [
        {"id": "universe", "type": "universe", "position": {"x": 40, "y": 40}, "variables": {}},
        {"id": "sc_1", "type": "scanner", "position": {"x": 300, "y": 40}, "variables": {"family": "vcp"}},
        {"id": "r_1", "type": "report", "position": {"x": 600, "y": 40}, "variables": {"min_rating": 0}},
    ],
    "edges": [
        {"id": "e1", "source": "universe", "sourceHandle": "out", "target": "sc_1", "targetHandle": "universe"},
        {"id": "e2", "source": "sc_1", "sourceHandle": "bucket", "target": "r_1", "targetHandle": "structural"},
    ],
}

INVALID_GRAPH = {
    "name": "broken",
    "nodes": [
        {"id": "universe", "type": "universe", "position": {"x": 0, "y": 0}, "variables": {}},
        {"id": "sc_1", "type": "scanner", "position": {"x": 100, "y": 0}, "variables": {}},
        {"id": "r_1", "type": "report", "position": {"x": 200, "y": 0}, "variables": {}},
    ],
    # edge from universe -> scanner has a bogus target port
    "edges": [
        {"id": "e1", "source": "universe", "sourceHandle": "out", "target": "sc_1", "targetHandle": "nope"},
        {"id": "e2", "source": "sc_1", "sourceHandle": "bucket", "target": "r_1", "targetHandle": "structural"},
    ],
}


@pytest.fixture
async def client():
    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_tools(client):
    resp = await client.get("/api/tools")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert [t["id"] for t in tools] == ["scanner", "quant", "search", "report"]
    assert "callable" not in tools[0]


# ── pipeline definitions ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_definitions_crud_roundtrip(client):
    created = await client.post("/api/definitions", json={"name": "vcp-lite", "graph": VALID_GRAPH})
    assert created.status_code == 201
    definition = created.json()
    assert definition["name"] == "vcp-lite"
    definition_id = definition["id"]

    listing = await client.get("/api/definitions")
    assert listing.status_code == 200
    assert any(d["id"] == definition_id for d in listing.json()["definitions"])

    fetched = await client.get(f"/api/definitions/{definition_id}")
    assert fetched.status_code == 200
    assert fetched.json()["graph"]["name"] == "vcp-lite"

    updated = await client.put(
        f"/api/definitions/{definition_id}",
        json={"name": "vcp-lite-v2", "graph": VALID_GRAPH},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "vcp-lite-v2"

    deleted = await client.delete(f"/api/definitions/{definition_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/definitions/{definition_id}")).status_code == 404


@pytest.mark.asyncio
async def test_create_definition_rejects_invalid_graph(client):
    resp = await client.post("/api/definitions", json={"name": "broken", "graph": INVALID_GRAPH})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any("target port" in e for e in detail)


@pytest.mark.asyncio
async def test_update_missing_definition_404(client):
    resp = await client.put("/api/definitions/does-not-exist", json={"name": "x", "graph": VALID_GRAPH})
    assert resp.status_code == 404
    resp = await client.delete("/api/definitions/does-not-exist")
    assert resp.status_code == 404


# ── component templates ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_component_templates_crud_roundtrip(client):
    created = await client.post(
        "/api/component-templates",
        json={"name": "vcp-tight", "component_id": "scanner", "variables": {"family": "vcp", "ep_limit": 100}},
    )
    assert created.status_code == 201
    template = created.json()
    assert template["component_id"] == "scanner"
    assert template["variables"]["family"] == "vcp"
    template_id = template["id"]

    listing = await client.get("/api/component-templates")
    assert any(t["id"] == template_id for t in listing.json()["templates"])

    updated = await client.put(
        f"/api/component-templates/{template_id}",
        json={"name": "vcp-tight", "component_id": "scanner", "variables": {"family": "vcp", "ep_limit": 50}},
    )
    assert updated.status_code == 200
    assert updated.json()["variables"]["ep_limit"] == 50

    assert (await client.delete(f"/api/component-templates/{template_id}")).status_code == 204
    assert (await client.get(f"/api/component-templates/{template_id}")).status_code == 404


@pytest.mark.asyncio
async def test_component_template_rejects_unknown_component(client):
    resp = await client.post(
        "/api/component-templates",
        json={"name": "x", "component_id": "not-a-tool", "variables": {}},
    )
    assert resp.status_code == 422
    assert "unknown component" in resp.json()["detail"]


# ── preview ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_graph_run_estimates_symbols(client):
    resp = await client.post(
        "/api/runs/preview",
        json={
            "name": "preview-me",
            "pipeline_type": "daily_bo_scan",
            "force_symbols": "AAPL, MSFT, NVDA",
            "graph": VALID_GRAPH,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["estimate"]["symbols"] == 3
    assert body["estimate"]["cost"] >= 0
    assert body["graph"]["nodes"] == 2  # scanner + report (universe excluded)


@pytest.mark.asyncio
async def test_preview_legacy_sweep(client):
    resp = await client.post(
        "/api/runs/preview",
        json={"name": "sweep", "pipeline_type": "daily_bo_scan", "use_screener": True, "force_symbols": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["estimate"]["symbols"] > 0


# ── graph run integration ────────────────────────────────────────────


def _fake_scanner_callable(inputs, params):
    """Replace the real scanner (no network): emit rated-lite scan rows."""
    out = []
    for r in inputs.get("universe", []):
        out.append(
            {
                "symbol": r.get("symbol"),
                "exchange": r.get("exchange") or "NASDAQ",
                "structural_rating": 4,
                "adv_20d": 5_000_000,
            }
        )
    return out


ZERO_QUANT_VARS = {
    "q_min_adv_dollar": 0,
    "q_min_market_cap": 0,
    "q_rs_floor": 0,
    "q_structural_floor": 0,
    "q_bo_min_impulse": 0,
    "q_bo_adr_lo": 0,
    "q_bo_adr_hi": 0,
    "q_bo_base_min": 0,
    "q_bo_base_max": 0,
    "q_bo_vci_max": 0,
    "q_bo_surfing": 0,
    "q_bo_surge_min": 0,
    "q_bo_dryup": 0,
}


def _canvas_graph(family: str = "vcp") -> dict:
    return {
        "name": f"{family}-lite",
        "nodes": [
            {"id": "universe", "type": "universe", "position": {"x": 40, "y": 40}, "variables": {}},
            {"id": "sc_1", "type": "scanner", "position": {"x": 300, "y": 40}, "variables": {"family": family}},
            {"id": "q_1", "type": "quant", "position": {"x": 450, "y": 40}, "variables": ZERO_QUANT_VARS},
            {"id": "r_1", "type": "report", "position": {"x": 600, "y": 40}, "variables": {"min_rating": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "universe", "sourceHandle": "out", "target": "sc_1", "targetHandle": "universe"},
            {"id": "e2", "source": "sc_1", "sourceHandle": "bucket", "target": "q_1", "targetHandle": "in"},
            {"id": "e3", "source": "q_1", "sourceHandle": "out", "target": "r_1", "targetHandle": "structural"},
        ],
    }


@pytest.mark.asyncio
async def test_graph_run_via_api_persists_artifacts_and_merge_table(monkeypatch):
    monkeypatch.setattr("stock_analyze.tools.builtins.SCANNER.callable", _fake_scanner_callable)

    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/runs",
            json={
                "name": "graph-run",
                "pipeline_type": "daily_bo_scan",
                "force_symbols": "AAPL, MSFT",
                "graph": _canvas_graph(),
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        await app.state.job_manager.tasks[run_id]

        detail = (await c.get(f"/api/runs/{run_id}")).json()
        assert detail["status"] == "succeeded"
        assert detail["counts"]["reports"] == 2

        artifacts = detail["artifacts"]
        assert artifacts["merge_table"]["count"] == 2
        symbols = {r["symbol"] for r in artifacts["merge_table"]["rows"]}
        assert symbols == {"AAPL", "MSFT"}

        # per-node artifacts staged under node:<node_id>
        assert "node:sc_1" in artifacts
        assert artifacts["node:sc_1"]["tool_id"] == "scanner"
        assert "node:q_1" in artifacts
        assert artifacts["node:r_1"]["tool_id"] == "report"
        assert artifacts["universe"]["config"]["source"] == "paste"

        # SSE terminal replay carries the merge table
        events = await c.get(f"/api/runs/{run_id}/events")
        assert events.status_code == 200
        assert "event: done" in events.text
        assert "merge_table" in events.text


@pytest.mark.asyncio
async def test_graph_run_by_definition_id(monkeypatch):
    monkeypatch.setattr("stock_analyze.tools.builtins.SCANNER.callable", _fake_scanner_callable)

    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        saved = await c.post("/api/definitions", json={"name": "saved-graph", "graph": _canvas_graph("ep")})
        definition_id = saved.json()["id"]

        resp = await c.post(
            "/api/runs",
            json={
                "name": "from-definition",
                "pipeline_type": "daily_bo_scan",
                "force_symbols": "TSLA",
                "definition_id": definition_id,
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]
        await app.state.job_manager.tasks[run_id]

        detail = (await c.get(f"/api/runs/{run_id}")).json()
        assert detail["status"] == "succeeded"
        assert detail["definition_id"] == definition_id
        assert detail["graph_snapshot"]["name"] == "ep-lite"
        assert detail["counts"]["reports"] == 1


@pytest.mark.asyncio
async def test_graph_run_rejects_invalid_graph():
    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/runs",
            json={"name": "bad", "pipeline_type": "daily_bo_scan", "force_symbols": "AAPL", "graph": INVALID_GRAPH},
        )
        assert resp.status_code == 422


# ── scan_id relaxation (Q8) ──────────────────────────────────────────


def test_snapshot_graph_run_without_scan_id_is_valid():
    from app.schemas import RunCreate
    from stock_analyze.tools import validate_graph
    from stock_analyze.tools.canvas import to_walker_definition

    # Schema: a snapshot universe no longer requires universe_scan_id.
    body = RunCreate(name="snap", universe_source="snapshot", graph=VALID_GRAPH)
    assert body.universe_scan_id is None

    # Walker: a snapshot definition with a null scan_id validates clean.
    definition = to_walker_definition(
        VALID_GRAPH,
        universe={"source": "snapshot", "force_keys": [], "scan_id": None},
    )
    assert not any("scan_id" in e for e in validate_graph(definition))

