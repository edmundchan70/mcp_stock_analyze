"""Canvas graph JSON <-> walker definition conversion (T20/T21).

The editor stores ReactFlow-shaped JSON (node ``type`` = tool id, edges with
``sourceHandle``/``targetHandle``, a dedicated ``universe`` node) while the
walker executes the flattened definition JSON. This module bridges the two
so ``POST /api/definitions`` stores the canvas shape and ``POST /api/runs``
runs it unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

from .registry import REGISTRY
from .walker import validate_graph

UNIVERSE_TYPE = "universe"

DEFAULT_UNIVERSE: dict[str, Any] = {
    "source": "paste",
    "force_keys": [],
    "scan_id": None,
}


def to_walker_definition(
    canvas_graph: dict[str, Any],
    universe: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Convert a canvas graph to the walker definition JSON shape."""
    nodes = canvas_graph.get("nodes") or []
    edges = canvas_graph.get("edges") or []

    universe_node_ids = {
        n["id"] for n in nodes if n.get("type") == UNIVERSE_TYPE
    }

    walker_nodes = [
        {
            "id": n["id"],
            "tool_id": n["type"],
            "params": dict(n.get("variables") or {}),
        }
        for n in nodes
        if n.get("type") != UNIVERSE_TYPE
    ]

    walker_edges = []
    for e in edges:
        src = "universe" if e.get("source") in universe_node_ids else e.get("source")
        walker_edges.append(
            {
                "id": e.get("id"),
                "source": src,
                "source_port": e.get("sourceHandle"),
                "target": e.get("target"),
                "target_port": e.get("targetHandle"),
            }
        )

    return {
        "version": 1,
        "name": canvas_graph.get("name") or "untitled",
        "universe": dict(universe or DEFAULT_UNIVERSE),
        "nodes": walker_nodes,
        "edges": walker_edges,
    }


def to_canvas_graph(definition: dict[str, Any]) -> dict[str, Any]:
    """Inverse conversion (used by editors to re-hydrate a run snapshot)."""
    nodes = list(definition.get("nodes") or [])
    edges = list(definition.get("edges") or [])

    canvas_nodes = [
        {
            "id": n["id"],
            "type": n["tool_id"],
            "position": {"x": 0, "y": 0},
            "variables": dict(n.get("params") or {}),
        }
        for n in nodes
    ]
    canvas_nodes.insert(0, {"id": "universe", "type": UNIVERSE_TYPE, "position": {"x": 40, "y": 40}, "variables": {}})

    canvas_edges = []
    for e in edges:
        src = "universe" if e.get("source") == "universe" else e.get("source")
        canvas_edges.append(
            {
                "id": e.get("id") or f"{src}:{e.get('source_port')}:{e.get('target')}:{e.get('target_port')}",
                "source": src,
                "sourceHandle": e.get("source_port"),
                "target": e.get("target"),
                "targetHandle": e.get("target_port"),
            }
        )

    return {
        "name": definition.get("name"),
        "nodes": canvas_nodes,
        "edges": canvas_edges,
    }


def validate_canvas_graph(
    canvas_graph: dict[str, Any],
    tools: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Validate a canvas graph; universe config is per-run so not required."""
    definition = to_walker_definition(canvas_graph, universe=DEFAULT_UNIVERSE)
    errors = validate_graph(definition, tools=tools or REGISTRY)
    # Universe is supplied at run time — drop the paste/snapshot complaints.
    return [e for e in errors if not e.startswith("universe.")]


__all__ = [
    "DEFAULT_UNIVERSE",
    "UNIVERSE_TYPE",
    "to_canvas_graph",
    "to_walker_definition",
    "validate_canvas_graph",
]
