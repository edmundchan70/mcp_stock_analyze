"""Graph walker — validate + execute a component graph definition (T19).

Canonical definition JSON::

    {
      "version": 1,
      "name": "...",
      "universe": {"source": "paste"|"snapshot", "force_keys": [["SYM","EX"]], "scan_id": null},
      "nodes": [{"id": "sc_1", "tool_id": "scanner", "params": {"family": "ep", ...}}],
      "edges": [{"id": "e1", "source": "sc_1", "source_port": "bucket",
                 "target": "q_1", "target_port": "in"}]
    }

Semantics (T11/T12): rows flow keyed by SymbolKey; every junction auto-merges
(``merge_rows``); a soft-fail row carries ``_error`` and is dropped from the
forward stream; a node callable that raises fails that node only (downstream
nodes receive empty input and the run is marked ``degraded``).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .control import RunCancelled, register_control, unregister_control
from .merge import merge_rows, to_merge_table
from .protocol import ERROR_KEY, ToolSpec, stage_accepts
from .registry import REGISTRY


class GraphValidationError(ValueError):
    pass


@dataclass
class NodeResult:
    node_id: str
    tool_id: str
    output_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    dropped: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    status: str = "ok"  # ok | error | skipped | cancelled


@dataclass
class GraphRunResult:
    order: list[str]
    nodes: dict[str, NodeResult]
    merge_table: dict[str, Any]
    degraded: bool = False
    cancelled: bool = False


def default_params(spec: ToolSpec) -> dict[str, Any]:
    return {v.key: v.default for v in spec.variables}


def _tool_params(spec: ToolSpec, node_params: dict[str, Any]) -> dict[str, Any]:
    params = default_params(spec)
    params.update({k: v for k, v in node_params.items() if v is not None})
    return params


# ── validation ───────────────────────────────────────────────────────


def validate_graph(
    definition: dict[str, Any],
    tools: Optional[dict[str, ToolSpec]] = None,
) -> list[str]:
    """Return a list of graph validation errors (empty when valid)."""
    tools = tools or REGISTRY
    errors: list[str] = []

    if definition.get("version") != 1:
        errors.append("unsupported graph version; expected 1")
    if not definition.get("name"):
        errors.append("graph requires a name")

    universe = definition.get("universe") or {}
    src = universe.get("source")
    if src not in ("paste", "snapshot"):
        errors.append("universe.source must be 'paste' or 'snapshot'")
    if src == "paste" and not universe.get("force_keys"):
        errors.append("universe.source=paste requires force_keys")

    nodes = definition.get("nodes") or []
    if not nodes:
        errors.append("graph requires at least one node")

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        nid = node.get("id")
        if not nid:
            errors.append("node missing id")
            continue
        if nid in nodes_by_id:
            errors.append(f"duplicate node id {nid!r}")
        nodes_by_id[nid] = node
        spec = tools.get(node.get("tool_id"))
        if spec is None:
            errors.append(f"node {nid!r}: unknown tool {node.get('tool_id')!r}")
            continue
        for key in node.get("params") or {}:
            var = next((v for v in spec.variables if v.key == key), None)
            if var is None:
                errors.append(f"node {nid!r}: unknown variable {key!r}")

    edges = definition.get("edges") or []
    edge_by_target: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        s, t = edge.get("source"), edge.get("target")
        sp, tp = edge.get("source_port"), edge.get("target_port")
        if s not in nodes_by_id and s != "universe":
            errors.append(f"edge {edge.get('id')!r}: unknown source node {s!r}")
        if t not in nodes_by_id:
            errors.append(f"edge {edge.get('id')!r}: unknown target node {t!r}")
            continue
        s_spec = None
        if s != "universe" and s in nodes_by_id:
            s_spec = tools.get(nodes_by_id[s].get("tool_id"))
        t_spec = tools.get(nodes_by_id[t].get("tool_id"))
        if t_spec is not None and t_spec.input(tp) is None:
            errors.append(f"edge {edge.get('id')!r}: target port {tp!r} not on {t_spec.id}")
        if s_spec is not None and s_spec.output(sp) is None:
            errors.append(f"edge {edge.get('id')!r}: source port {sp!r} not on {s_spec.id}")
        if s_spec is not None and t_spec is not None:
            out_port, in_port = s_spec.output(sp), t_spec.input(tp)
            if out_port and in_port and not stage_accepts(in_port.type, out_port.type):
                errors.append(
                    f"edge {edge.get('id')!r}: {s}:{sp}({out_port.type}) -> "
                    f"{t}:{tp}({in_port.type}) - port type not accepted"
                )
        edge_by_target.setdefault(t, []).append(edge)

    # Required input ports must be fed (edge or implicit universe symbolkey).
    for node in nodes:
        nid = node.get("id")
        spec = tools.get(node.get("tool_id"))
        if spec is None:
            continue
        fed = {e.get("target_port") for e in edge_by_target.get(nid, [])}
        for port in spec.inputs:
            if port.required and port.id not in fed:
                if port.type == "symbolkey":
                    continue  # fed by the implicit universe node
                errors.append(f"node {nid!r}: required input port {port.id!r} not fed")

    cycle = find_cycle(edges, nodes_by_id)
    if cycle:
                errors.append(f"graph contains a cycle: {' -> '.join(cycle)}")

    return errors


def find_cycle(
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, Any],
) -> Optional[list[str]]:
    """Kahn topo sort; returns one cycle path or None."""
    adj: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
    indeg = {nid: 0 for nid in nodes_by_id}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s == "universe" or s not in adj or t not in adj:
            continue
        adj[s].append(t)
        indeg[t] += 1
    q = deque(nid for nid, d in indeg.items() if d == 0)
    seen = 0
    while q:
        nid = q.popleft()
        seen += 1
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if seen == len(indeg):
        return None
    # Build one cycle by walking from a node with remaining indegree.
    cycle: list[str] = []
    start = next(nid for nid, d in indeg.items() if d > 0)
    cur = start
    while True:
        cycle.append(cur)
        cur = next(t for s, t in ((e.get("source"), e.get("target")) for e in edges)
                   if s == cur and t in indeg and indeg[t] > 0)
        if cur in cycle:
            cycle = cycle[cycle.index(cur):] + [cur]
            return cycle


def topological_order(
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, Any],
) -> list[str]:
    cycle = find_cycle(edges, nodes_by_id)
    if cycle:
        raise GraphValidationError(f"graph contains a cycle: {' -> '.join(cycle)}")
    adj: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
    indeg = {nid: 0 for nid in nodes_by_id}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s == "universe" or s not in adj or t not in adj:
            continue
        adj[s].append(t)
        indeg[t] += 1
    q = deque(nid for nid, d in indeg.items() if d == 0)
    order: list[str] = []
    while q:
        nid = q.popleft()
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    return order


# ── execution ────────────────────────────────────────────────────────


def run_graph(
    definition: dict[str, Any],
    universe_rows: list[dict[str, Any]],
    *,
    tools: Optional[dict[str, ToolSpec]] = None,
    node_overrides: Optional[dict[str, dict[str, Any]]] = None,
    on_node: Optional[Callable[[str, str, str, int, int], None]] = None,
    control: Optional[Any] = None,
    on_confirm: Optional[Callable[[str, int, int], None]] = None,
    progress: Optional[Any] = None,
) -> GraphRunResult:
    """Execute a graph definition over ``universe_rows``.

    ``on_node(node_id, tool_id, status, kept, total)`` fires per node
    (status ``running``/``ok``/``error``/``skipped``/``cancelled``) — wired to
    SSE progress. ``control`` (a ``RunControl`` duck-type) enables runtime
    skip/pause/cancel + the AI Search confirmation gate; ``on_confirm(node_id,
    symbol_count, tavily_estimate)`` fires when the gate blocks.

    ``progress`` is a ``RunProgress`` duck-type (or ``None``) streamed to node
    callables via an injected ``__progress__`` param so per-symbol stages
    (symbol resolution, batch OHLCV, scoring, enrichment) surface on SSE. It is
    injected at execution time only and never persisted with ``params``.
    """
    tools = tools or REGISTRY
    errors = validate_graph(definition, tools=tools)
    if errors:
        raise GraphValidationError("; ".join(errors))

    nodes_by_id = {n.get("id"): n for n in definition["nodes"]}
    order = topological_order(definition.get("edges") or [], nodes_by_id)
    edges = definition.get("edges") or []

    control_id = register_control(control) if control is not None else None

    out_by_node: dict[str, dict[str, list[dict[str, Any]]]] = {}
    results: dict[str, NodeResult] = {}
    degraded = False
    cancelled = False
    report_rows: list[dict[str, Any]] = []

    try:
        for nid in order:
            node = nodes_by_id[nid]
            spec = tools[node["tool_id"]]
            params = _tool_params(spec, node.get("params") or {})
            if node_overrides and nid in node_overrides:
                params.update(node_overrides[nid])
            if control_id is not None:
                params["__control_id__"] = control_id
            if progress is not None:
                params["__progress__"] = progress

            # Assemble per-port inputs (auto-merge at junctions).
            inputs: dict[str, list[dict[str, Any]]] = {}
            fed: set[str] = set()
            for e in edges:
                if e.get("target") != nid:
                    continue
                t_port = e["target_port"]
                fed.add(t_port)
                src = e.get("source")
                s_port = e.get("source_port")
                if src == "universe":
                    group = [dict(r) for r in universe_rows]
                else:
                    group = out_by_node.get(src, {}).get(s_port, [])
                inputs[t_port] = merge_rows(inputs.get(t_port, []), group)
            for port in spec.inputs:
                if port.type == "symbolkey" and port.id not in fed:
                    inputs[port.id] = [dict(r) for r in universe_rows]

            result = NodeResult(node_id=nid, tool_id=spec.id)
            primary = _primary_input(inputs)

            # Skip (pre-emptive): pass rows through unchanged, mark skipped.
            if control is not None and control.is_skipped(nid):
                result.status = "skipped"
                _store_outputs(spec, result, primary)
                results[nid] = result
                out_by_node[nid] = result.output_rows
                _collect_report_rows(spec, result, nid, report_rows)
                if on_node is not None:
                    on_node(nid, spec.id, "skipped", len(primary), len(primary))
                continue

            # Pause checkpoint between nodes (blocks while paused, cancels).
            if control is not None:
                control.checkpoint()

            # AI Search confirmation gate: block before a large search batch.
            if spec.id == "search" and control is not None:
                threshold = int(params.get("confirm_threshold") or 0)
                if threshold > 0 and len(primary) > threshold and not control.is_skipped(nid):
                    tavily = len(primary) * 2
                    control.request_confirmation(nid, len(primary), tavily)
                    if on_confirm is not None:
                        on_confirm(nid, len(primary), tavily)
                    decision = control.wait_confirmation(nid)
                    if decision == "skip":
                        result.status = "skipped"
                        _store_outputs(spec, result, primary)
                        results[nid] = result
                        out_by_node[nid] = result.output_rows
                        _collect_report_rows(spec, result, nid, report_rows)
                        if on_node is not None:
                            on_node(nid, spec.id, "skipped", len(primary), len(primary))
                        continue
                    if decision == "cancel":
                        raise RunCancelled()

            if on_node is not None:
                on_node(nid, spec.id, "running", 0, 0)
            started = time.perf_counter()

            try:
                rows = spec.callable(inputs, params) if spec.callable else []
            except RunCancelled:
                result.status = "cancelled"
                results[nid] = result
                out_by_node[nid] = result.output_rows
                if on_node is not None:
                    on_node(nid, spec.id, "cancelled", 0, 0)
                raise
            except Exception as exc:  # node-level failure → degrade, keep going
                result.error = str(exc)
                result.status = "error"
                degraded = True
                _store_outputs(spec, result, [])
                result.duration_ms = int((time.perf_counter() - started) * 1000)
                results[nid] = result
                out_by_node[nid] = result.output_rows
                if on_node is not None:
                    on_node(nid, spec.id, "error", 0, 0)
                continue

            fwd, soft = _split_soft_failures(rows)
            result.dropped = len(soft)
            result.errors = _clean_errors(soft)
            if spec.id == "scanner":
                lane = str(params.get("family") or spec.id)
                for r in fwd:
                    r["_lane"] = lane
            _store_outputs(spec, result, fwd)
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            results[nid] = result
            out_by_node[nid] = result.output_rows

            if on_node is not None:
                on_node(nid, spec.id, "ok", len(fwd), len(rows))

            _collect_report_rows(spec, result, nid, report_rows)
    except RunCancelled:
        cancelled = True
    finally:
        if control_id is not None:
            unregister_control(control_id)

    table = to_merge_table(report_rows)
    return GraphRunResult(
        order=order,
        nodes=results,
        merge_table=table,
        degraded=degraded,
        cancelled=cancelled,
    )


def _primary_input(inputs: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge every fed input port into a single row list (skip pass-through)."""
    merged: list[dict[str, Any]] = []
    for rows in inputs.values():
        merged = merge_rows(merged, rows)
    return merged


def _collect_report_rows(
    spec: ToolSpec,
    result: NodeResult,
    nid: str,
    report_rows: list[dict[str, Any]],
) -> None:
    for p_id, rows_out in result.output_rows.items():
        port = spec.output(p_id)
        if port is not None and port.type == "report_rows":
            report_rows.extend({**r, "_source": nid} for r in rows_out)


def _store_outputs(
    spec: ToolSpec, result: NodeResult, rows: list[dict[str, Any]]
) -> None:
    for port in spec.outputs:
        result.output_rows[port.id] = [dict(r) for r in rows]


def _split_soft_failures(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fwd, soft = [], []
    for r in rows:
        if isinstance(r, dict) and r.get(ERROR_KEY):
            soft.append(r)
        else:
            fwd.append(r)
    return fwd, soft


def _clean_errors(soft: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in soft:
        item = {k: v for k, v in r.items() if k != ERROR_KEY}
        item["error"] = r.get(ERROR_KEY, "soft-fail")
        out.append(item)
    return out


__all__ = [
    "GraphRunResult",
    "GraphValidationError",
    "NodeResult",
    "default_params",
    "find_cycle",
    "run_graph",
    "topological_order",
    "validate_graph",
]
