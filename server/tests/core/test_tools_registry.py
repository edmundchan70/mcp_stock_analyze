"""Tool registry, port-stage matrix, row merge + lane-merge table, preview (T28)."""

from __future__ import annotations

import json

from stock_analyze.tools import (
    REGISTRY,
    get_tool,
    get_tools,
    registry_payload,
    validate_registry,
)
from stock_analyze.tools.merge import merge_rows, symbol_key, to_merge_table
from stock_analyze.tools.preview import estimate_graph_run, estimate_symbol_count
from stock_analyze.tools.protocol import stage_accepts


def test_registry_holds_four_builtins():
    ids = [t.id for t in get_tools()]
    assert ids == ["scanner", "quant", "search", "report"]


def test_registry_is_phase_sorted():
    phases = [t.phase for t in get_tools()]
    assert phases == sorted(phases)


def test_get_tool_lookup():
    assert get_tool("scanner").name == "Scanner"
    assert get_tool("missing") is None


def test_validate_registry_passes():
    assert validate_registry() == []


def test_registry_payload_is_json_safe():
    payload = registry_payload()
    blob = json.dumps(payload)  # must not raise (no pydantic models / datetimes)
    assert len(json.loads(blob)) == 4
    for spec in payload:
        assert set(spec) >= {"id", "name", "description", "phase", "inputs", "outputs", "variables"}
        assert spec["phase"] in (1, 2, 3, 4)


def test_toolspec_to_dict_drops_callable():
    spec = get_tool("scanner").to_dict()
    assert "callable" not in spec
    assert spec["id"] == "scanner"


def test_stage_accepts_matrix():
    assert stage_accepts("symbolkey", "symbolkey")
    assert stage_accepts("filtered_rows", "scan_rows")
    assert stage_accepts("filtered_rows", "filtered_rows")
    assert stage_accepts("enriched_rows", "scan_rows")
    assert stage_accepts("enriched_rows", "filtered_rows")
    assert stage_accepts("report_rows", "scan_rows")
    assert stage_accepts("report_rows", "enriched_rows")
    # stage regression is never legal
    assert not stage_accepts("scan_rows", "filtered_rows")
    assert not stage_accepts("symbolkey", "scan_rows")
    assert not stage_accepts("unknown", "scan_rows")


def test_symbol_key_normalizes_case_and_exchange():
    assert symbol_key({"symbol": "aapl", "exchange": "nasdaq"}) == ("AAPL", "NASDAQ")
    assert symbol_key({"symbol": "MSFT"}) == ("MSFT", "NASDAQ")


def test_merge_rows_dedupes_first_wins():
    a = {"symbol": "AAPL", "exchange": "NASDAQ", "price": 100}
    b = {"symbol": "aapl", "price": 200}  # same key, later group
    out = merge_rows([a], [b])
    assert out == [a]  # first occurrence wins


def test_merge_rows_keep_selector():
    low = {"symbol": "AAPL", "rating": 1}
    high = {"symbol": "AAPL", "rating": 5}
    assert merge_rows([low], [high], keep=lambda r: r.get("rating", 0)) == [high]


def test_to_merge_table_lane_join_and_rating_precedence():
    rows = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "rating": 4, "_source": "r_1", "_lane": "vcp"},
        {"symbol": "AAPL", "exchange": "NASDAQ", "rating": 3, "_source": "r_2", "_lane": "ep"},
        {"symbol": "MSFT", "exchange": "NASDAQ", "rating": 5, "_source": "r_2", "_lane": "ep"},
    ]
    table = to_merge_table(rows)
    assert table["count"] == 2
    by_symbol = {r["symbol"]: r for r in table["rows"]}
    assert by_symbol["AAPL"]["rating"] == 4  # max rating wins
    assert "vcp" in by_symbol["AAPL"]["lanes"] and "ep" in by_symbol["AAPL"]["lanes"]
    assert by_symbol["MSFT"]["lanes"] == "ep"
    # primary columns first
    assert table["columns"][:4] == ["symbol", "exchange", "rating", "lanes"]
    # sorted by rating desc
    assert table["rows"][0]["symbol"] == "MSFT"


def test_to_merge_table_strips_walker_markers():
    table = to_merge_table([{"symbol": "TSLA", "_source": "r_1", "rating": 4}])
    row = table["rows"][0]
    assert "_source" not in row
    assert "_lane" not in row


def test_estimate_symbol_count():
    assert estimate_symbol_count({"source": "paste"}, "aapl, nvda, msft") == 3
    assert estimate_symbol_count({"source": "paste"}, " aapl \n nvda ") == 2
    assert estimate_symbol_count({"source": "paste"}, "") == 1
    assert estimate_symbol_count({"source": "snapshot"}) == 3000


def test_estimate_graph_run_counts_nodes():
    definition = {
        "nodes": [
            {"id": "sc_1", "tool_id": "scanner", "params": {}},
            {"id": "s_1", "tool_id": "search", "params": {}},
        ],
        "edges": [],
    }
    est = estimate_graph_run(definition, symbol_count=100)
    assert est["symbols"] == 100
    assert est["cost"] > 0  # search LLM calls add cost
    node_ids = {n["node_id"] for n in est["nodes"]}
    assert node_ids == {"sc_1", "s_1"}


def test_estimate_graph_run_warns_on_large_runs():
    definition = {"nodes": [{"id": "s_1", "tool_id": "search", "params": {}}], "edges": []}
    est = estimate_graph_run(definition, symbol_count=200)
    assert any("exceeds 10 minutes" in w for w in est["warnings"])
