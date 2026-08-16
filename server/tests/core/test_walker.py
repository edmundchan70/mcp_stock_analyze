"""Graph walker tests: validation, topo order, fan-out, merge, soft-fail (T28)."""

from __future__ import annotations

from stock_analyze.tools.protocol import ERROR_KEY, PortDef, ToolSpec, VariableDef
from stock_analyze.tools.walker import (
    GraphValidationError,
    default_params,
    find_cycle,
    run_graph,
    topological_order,
    validate_graph,
)

# ── fake tools (no network; pure in-memory callables) ────────────────


def _port(pid, ptype, required=True):
    return PortDef(id=pid, type=ptype, required=required, label=pid)


def _scanner(inputs, params):
    return [dict(r) for r in inputs.get("universe", []) if r.get("symbol")]


def _quant(inputs, params):
    keep = float(params.get("min_rating", 0))
    out = []
    for r in inputs.get("in", []):
        r = dict(r)
        rating = float(r.get("rating") or 0)
        if rating < keep:
            r[ERROR_KEY] = "below min rating"
        out.append(r)
    return out


def _search(inputs, params):
    out = []
    for r in inputs.get("in", []):
        r = dict(r)
        r["enrichment"] = {"source": "fake"}
        out.append(r)
    return out


def _report(inputs, params):
    rows = inputs.get("structural") or inputs.get("in") or []
    return [
        {**r, "rating": float(r.get("rating") or params.get("rating", 4))}
        for r in rows
    ]


FAKE_TOOLS: dict[str, ToolSpec] = {
    "scanner": ToolSpec(
        id="scanner", name="Scanner", description="", phase=1,
        inputs=[_port("universe", "symbolkey")],
        outputs=[_port("bucket", "scan_rows")],
        variables=[VariableDef(key="family", label="family", kind="select", default="ep", group="Family", options=["ep", "vcp", "bo", "custom"])],
        callable=_scanner,
    ),
    "quant": ToolSpec(
        id="quant", name="Quant", description="", phase=2,
        inputs=[_port("in", "filtered_rows")],
        outputs=[_port("out", "filtered_rows")],
        variables=[VariableDef(key="min_rating", label="min", kind="number", default=0, group="filters")],
        callable=_quant,
    ),
    "search": ToolSpec(
        id="search", name="AI Search", description="", phase=3,
        inputs=[_port("in", "enriched_rows")],
        outputs=[_port("out", "enriched_rows")],
        callable=_search,
    ),
    "report": ToolSpec(
        id="report", name="Report", description="", phase=4,
        inputs=[
            _port("structural", "report_rows"),
            _port("context", "enriched_rows", required=False),
        ],
        outputs=[_port("rated", "report_rows")],
        callable=_report,
    ),
}


def _definition(nodes=None, edges=None, name="g", quant_params=None):
    return {
        "version": 1,
        "name": name,
        "universe": {"source": "paste", "force_keys": [["AAPL", "NASDAQ"]], "scan_id": None},
        "nodes": nodes
        if nodes is not None
        else [
            {"id": "sc_1", "tool_id": "scanner", "params": {}},
            {"id": "q_1", "tool_id": "quant", "params": quant_params if quant_params is not None else {"min_rating": 0}},
            {"id": "r_1", "tool_id": "report", "params": {}},
        ],
        "edges": edges
        if edges is not None
        else [
            {"id": "e1", "source": "universe", "source_port": "out", "target": "sc_1", "target_port": "universe"},
            {"id": "e2", "source": "sc_1", "source_port": "bucket", "target": "q_1", "target_port": "in"},
            {"id": "e3", "source": "q_1", "source_port": "out", "target": "r_1", "target_port": "structural"},
        ],
    }


UNIVERSE = [
    {"symbol": "AAPL", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "exchange": "NASDAQ"},
]


# ── validation ───────────────────────────────────────────────────────


def test_validate_graph_accepts_valid_definition():
    assert validate_graph(_definition(), tools=FAKE_TOOLS) == []


def test_validate_graph_unknown_tool():
    d = _definition(nodes=[{"id": "x", "tool_id": "nope", "params": {}}], edges=[])
    errors = validate_graph(d, tools=FAKE_TOOLS)
    assert any("unknown tool" in e for e in errors)


def test_validate_graph_unknown_variable():
    d = _definition(
        nodes=[{"id": "q_1", "tool_id": "quant", "params": {"not_a_var": 1}}],
        edges=[],
    )
    errors = validate_graph(d, tools=FAKE_TOOLS)
    assert any("unknown variable" in e for e in errors)


def test_validate_graph_cycle():
    d = _definition(
        nodes=[
            {"id": "a", "tool_id": "quant", "params": {}},
            {"id": "b", "tool_id": "quant", "params": {}},
        ],
        edges=[
            {"id": "e1", "source": "a", "source_port": "out", "target": "b", "target_port": "in"},
            {"id": "e2", "source": "b", "source_port": "out", "target": "a", "target_port": "in"},
        ],
    )
    errors = validate_graph(d, tools=FAKE_TOOLS)
    assert any("cycle" in e for e in errors)


def test_validate_graph_unfed_required_port():
    # quant requires 'in' but nothing feeds it
    d = _definition(
        nodes=[{"id": "q_1", "tool_id": "quant", "params": {}}],
        edges=[],
    )
    errors = validate_graph(d, tools=FAKE_TOOLS)
    assert any("required input port" in e for e in errors)


def test_validate_graph_port_stage_mismatch():
    # report emits report_rows; feeding those into quant's filtered_rows is illegal
    d = _definition(
        nodes=[
            {"id": "r_1", "tool_id": "report", "params": {}},
            {"id": "q_1", "tool_id": "quant", "params": {}},
        ],
        edges=[
            {"id": "e1", "source": "r_1", "source_port": "rated", "target": "q_1", "target_port": "in"},
        ],
    )
    errors = validate_graph(d, tools=FAKE_TOOLS)
    assert any("port type not accepted" in e for e in errors)


def test_find_cycle_and_topological_order():
    edges = [
        {"id": "e1", "source": "a", "target": "b"},
        {"id": "e2", "source": "b", "target": "c"},
    ]
    nodes = {"a": {}, "b": {}, "c": {}}
    assert find_cycle(edges, nodes) is None
    assert topological_order(edges, nodes) == ["a", "b", "c"]

    cyclic = [
        {"id": "e1", "source": "a", "target": "b"},
        {"id": "e2", "source": "b", "target": "a"},
    ]
    assert find_cycle(cyclic, nodes) is not None
    try:
        topological_order(cyclic, nodes)
        raise AssertionError("expected GraphValidationError")
    except GraphValidationError:
        pass


def test_default_params_uses_variable_defaults():
    spec = FAKE_TOOLS["quant"]
    assert default_params(spec) == {"min_rating": 0}


# ── execution ────────────────────────────────────────────────────────


def test_run_graph_topo_order_and_merge_table():
    result = run_graph(_definition(), UNIVERSE, tools=FAKE_TOOLS)
    assert result.order == ["sc_1", "q_1", "r_1"]
    assert result.degraded is False
    assert result.merge_table["count"] == 3
    ratings = {r["symbol"]: r["rating"] for r in result.merge_table["rows"]}
    assert ratings == {"AAPL": 4, "MSFT": 4, "NVDA": 4}
    # report rows inherit the scanner-family lane
    assert result.merge_table["rows"][0]["lanes"] == "ep"


def test_run_graph_soft_failures_recorded_and_dropped():
    # quant min_rating=5 drops all rows below it as soft-fails
    d = _definition(quant_params={"min_rating": 5})
    result = run_graph(d, UNIVERSE, tools=FAKE_TOOLS)
    q = result.nodes["q_1"]
    assert q.dropped == 3
    assert len(q.errors) == 3
    assert all(e["error"] == "below min rating" for e in q.errors)
    # soft-failed rows never reach the report
    assert result.merge_table["count"] == 0


def test_run_graph_node_exception_degrades_but_keeps_going():
    def boom(inputs, params):
        raise RuntimeError("oh no")

    tools = {**FAKE_TOOLS, "quant": ToolSpec(
        id="quant", name="Quant", description="", phase=2,
        inputs=[_port("in", "filtered_rows")],
        outputs=[_port("out", "filtered_rows")],
        callable=boom,
    )}
    result = run_graph(_definition(quant_params={}), UNIVERSE, tools=tools)
    assert result.degraded is True
    assert result.nodes["q_1"].error == "oh no"
    # report still runs with empty input (no crash)
    assert result.merge_table["count"] == 0


def test_run_graph_fan_out_copies_row_streams():
    # two quant nodes fed from one scanner — both receive the same rows
    d = _definition(
        nodes=[
            {"id": "sc_1", "tool_id": "scanner", "params": {}},
            {"id": "q_a", "tool_id": "quant", "params": {"min_rating": 0}},
            {"id": "q_b", "tool_id": "quant", "params": {"min_rating": 0}},
        ],
        edges=[
            {"id": "e1", "source": "universe", "source_port": "out", "target": "sc_1", "target_port": "universe"},
            {"id": "e2", "source": "sc_1", "source_port": "bucket", "target": "q_a", "target_port": "in"},
            {"id": "e3", "source": "sc_1", "source_port": "bucket", "target": "q_b", "target_port": "in"},
        ],
    )
    result = run_graph(d, UNIVERSE, tools=FAKE_TOOLS)
    assert result.order == ["sc_1", "q_a", "q_b"]
    assert len(result.nodes["q_a"].output_rows["out"]) == 3
    assert len(result.nodes["q_b"].output_rows["out"]) == 3


def test_run_graph_auto_merge_at_junction():
    # two scanners feed one quant 'in' port; overlapping symbol deduped
    d = _definition(
        nodes=[
            {"id": "sc_a", "tool_id": "scanner", "params": {"family": "ep"}},
            {"id": "sc_b", "tool_id": "scanner", "params": {"family": "vcp"}},
            {"id": "q_1", "tool_id": "quant", "params": {"min_rating": 0}},
            {"id": "r_1", "tool_id": "report", "params": {}},
        ],
        edges=[
            {"id": "e1", "source": "universe", "source_port": "out", "target": "sc_a", "target_port": "universe"},
            {"id": "e2", "source": "universe", "source_port": "out", "target": "sc_b", "target_port": "universe"},
            {"id": "e3", "source": "sc_a", "source_port": "bucket", "target": "q_1", "target_port": "in"},
            {"id": "e4", "source": "sc_b", "source_port": "bucket", "target": "q_1", "target_port": "in"},
            {"id": "e5", "source": "q_1", "source_port": "out", "target": "r_1", "target_port": "structural"},
        ],
    )
    result = run_graph(d, UNIVERSE, tools=FAKE_TOOLS)
    # both scanners emit all 3 symbols; junction merges to 3, not 6
    assert len(result.nodes["q_1"].output_rows["out"]) == 3


def test_run_graph_scanner_stamps_lane():
    d = _definition(
        nodes=[{"id": "sc_1", "tool_id": "scanner", "params": {"family": "vcp"}}],
        edges=[{"id": "e1", "source": "universe", "source_port": "out", "target": "sc_1", "target_port": "universe"}],
    )
    result = run_graph(d, UNIVERSE, tools=FAKE_TOOLS)
    rows = result.nodes["sc_1"].output_rows["bucket"]
    assert all(r.get("_lane") == "vcp" for r in rows)


def test_run_graph_on_node_callbacks():
    events: list[tuple] = []
    result = run_graph(
        _definition(),
        UNIVERSE,
        tools=FAKE_TOOLS,
        on_node=lambda nid, tid, status, kept, total: events.append((nid, status, kept)),
    )
    assert len(result.order) == 3
    ok_events = [e for e in events if e[1] == "ok"]
    assert len(ok_events) == 3


def test_run_graph_invalid_definition_raises():
    d = _definition(nodes=[{"id": "x", "tool_id": "nope", "params": {}}], edges=[])
    try:
        run_graph(d, UNIVERSE, tools=FAKE_TOOLS)
        raise AssertionError("expected GraphValidationError")
    except GraphValidationError as exc:
        assert "unknown tool" in str(exc)
