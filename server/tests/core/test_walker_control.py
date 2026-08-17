"""Walker runtime-control tests: skip pass-through, cancel, confirmation gate."""

from __future__ import annotations

from stock_analyze.tools.control import RunCancelled
from stock_analyze.tools.protocol import PortDef, ToolSpec, VariableDef
from stock_analyze.tools.walker import run_graph


def _port(pid, ptype, required=True):
    return PortDef(id=pid, type=ptype, required=required, label=pid)


def _scanner(inputs, params):
    return [dict(r) for r in inputs.get("universe", []) if r.get("symbol")]


def _search(inputs, params):
    out = []
    for r in inputs.get("in", []):
        r = dict(r)
        r["enrichment"] = {"source": "fake"}
        out.append(r)
    return out


def _report(inputs, params):
    rows = inputs.get("structural") or inputs.get("in") or []
    return [{**r, "rating": 4} for r in rows]


FAKE_TOOLS: dict[str, ToolSpec] = {
    "scanner": ToolSpec(
        id="scanner", name="Scanner", description="", phase=1,
        inputs=[_port("universe", "symbolkey")],
        outputs=[_port("bucket", "scan_rows")],
        variables=[VariableDef(key="family", label="family", kind="select", default="ep", group="Family", options=["ep", "vcp", "bo"])],
        callable=_scanner,
    ),
    "search": ToolSpec(
        id="search", name="AI Search", description="", phase=3,
        inputs=[_port("in", "enriched_rows")],
        outputs=[_port("out", "enriched_rows")],
        variables=[VariableDef(key="confirm_threshold", label="Confirm above N", kind="number", default=50, group="Confirmation")],
        callable=_search,
    ),
    "report": ToolSpec(
        id="report", name="Report", description="", phase=4,
        inputs=[_port("structural", "report_rows"), _port("context", "enriched_rows", required=False)],
        outputs=[_port("rated", "report_rows")],
        callable=_report,
    ),
}


def _definition(confirm_threshold=None):
    search_params = {}
    if confirm_threshold is not None:
        search_params["confirm_threshold"] = confirm_threshold
    return {
        "version": 1,
        "name": "g",
        "universe": {"source": "paste", "force_keys": [["AAPL", "NASDAQ"]], "scan_id": None},
        "nodes": [
            {"id": "sc_1", "tool_id": "scanner", "params": {}},
            {"id": "sr_1", "tool_id": "search", "params": search_params},
            {"id": "r_1", "tool_id": "report", "params": {}},
        ],
        "edges": [
            {"id": "e1", "source": "universe", "source_port": "out", "target": "sc_1", "target_port": "universe"},
            {"id": "e2", "source": "sc_1", "source_port": "bucket", "target": "sr_1", "target_port": "in"},
            {"id": "e3", "source": "sr_1", "source_port": "out", "target": "r_1", "target_port": "structural"},
        ],
    }


UNIVERSE = [
    {"symbol": "AAPL", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "exchange": "NASDAQ"},
]


class FakeControl:
    def __init__(self):
        self._skip: set[str] = set()
        self._decisions: dict[str, str] = {}
        self._checkpoint_calls = 0
        self.cancel_at: int | None = None

    def arm_skip(self, node_id: str) -> None:
        self._skip.add(node_id)

    def is_skipped(self, node_id: str) -> bool:
        return node_id in self._skip

    def checkpoint(self) -> None:
        self._checkpoint_calls += 1
        if self.cancel_at is not None and self._checkpoint_calls >= self.cancel_at:
            raise RunCancelled()

    def request_confirmation(self, node_id, symbol_count, tavily_estimate) -> None:
        pass

    def wait_confirmation(self, node_id: str) -> str | None:
        return self._decisions.get(node_id)

    def confirm(self, node_id: str, decision: str) -> None:
        self._decisions[node_id] = decision


def test_skip_pass_through_marks_node_skipped_and_report_still_runs():
    control = FakeControl()
    control.arm_skip("sr_1")

    result = run_graph(_definition(), UNIVERSE, tools=FAKE_TOOLS, control=control)

    assert result.cancelled is False
    sr = result.nodes["sr_1"]
    assert sr.status == "skipped"
    # pass-through: the scanner rows flowed through unchanged
    assert {r["symbol"] for r in sr.output_rows["out"]} == {"AAPL", "MSFT", "NVDA"}
    assert result.merge_table["count"] == 3


def test_cancel_between_nodes_returns_partial_cancelled_result():
    control = FakeControl()
    control.cancel_at = 2  # scanner checkpoint ok, search checkpoint raises

    result = run_graph(_definition(), UNIVERSE, tools=FAKE_TOOLS, control=control)

    assert result.cancelled is True
    assert "sc_1" in result.nodes  # completed before cancel
    assert "sr_1" not in result.nodes


def test_confirmation_gate_skip_decision_passes_through():
    control = FakeControl()
    control.confirm("sr_1", "skip")

    # 3 symbols > threshold 1 → gate fires; decision = skip
    result = run_graph(_definition(confirm_threshold=1), UNIVERSE, tools=FAKE_TOOLS, control=control)

    assert result.cancelled is False
    assert result.nodes["sr_1"].status == "skipped"
    assert result.merge_table["count"] == 3


def test_confirmation_gate_cancel_decision_cancels_run():
    control = FakeControl()
    control.confirm("sr_1", "cancel")

    result = run_graph(_definition(confirm_threshold=1), UNIVERSE, tools=FAKE_TOOLS, control=control)

    assert result.cancelled is True
    assert "sr_1" not in result.nodes


def test_confirmation_gate_proceed_runs_normally():
    control = FakeControl()
    control.confirm("sr_1", "proceed")

    result = run_graph(_definition(confirm_threshold=1), UNIVERSE, tools=FAKE_TOOLS, control=control)

    assert result.cancelled is False
    assert result.nodes["sr_1"].status == "ok"
    assert result.merge_table["count"] == 3


def test_confirmation_gate_skipped_when_skip_armed():
    control = FakeControl()
    control.arm_skip("sr_1")
    # skip-wins: no decision needed, gate suppressed
    result = run_graph(_definition(confirm_threshold=1), UNIVERSE, tools=FAKE_TOOLS, control=control)

    assert result.nodes["sr_1"].status == "skipped"
    assert result.cancelled is False


def test_run_without_control_has_no_cancel_or_skip():
    result = run_graph(_definition(), UNIVERSE, tools=FAKE_TOOLS)
    assert result.cancelled is False
    assert result.nodes["sr_1"].status == "ok"
