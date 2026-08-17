"""Prebuilt daily pipeline presets (Q1-Q10).

Three full-chain canvas graphs (Universe -> Scanner -> AI Search -> Report) are
seeded into ``pipeline_definitions`` on server boot. Seeding is idempotent by
name: existing definitions (including user-edited ones) are never overwritten,
and deletions are re-created on the next boot. The universe-source default is
carried as a ``defaults.universe_source`` hint in the graph JSON (the walker
ignores extra top-level keys).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _node(
    node_id: str,
    node_type: str,
    x: int,
    y: int,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "position": {"x": x, "y": y}, "variables": variables or {}}


def _chain_graph(name: str, family: str, universe_source: str) -> dict[str, Any]:
    """Build the canonical daily chain: Universe -> Scanner -> Search -> Report."""
    return {
        "name": name,
        "defaults": {"universe_source": universe_source},
        "nodes": [
            _node("universe", "universe", 40, 200),
            _node("sc_1", "scanner", 300, 40, {"family": family}),
            _node("sr_1", "search", 460, 40),
            _node("r_1", "report", 620, 40),
        ],
        "edges": [
            {"id": "e1", "source": "universe", "sourceHandle": "out", "target": "sc_1", "targetHandle": "universe"},
            {"id": "e2", "source": "sc_1", "sourceHandle": "bucket", "target": "sr_1", "targetHandle": "in"},
            {"id": "e3", "source": "sr_1", "sourceHandle": "out", "target": "r_1", "targetHandle": "structural"},
        ],
    }


PRESET_DEFINITIONS: list[dict[str, Any]] = [
    _chain_graph("Daily VCP Scan", "vcp", "paste"),
    _chain_graph("Daily BO Scan", "bo", "snapshot"),
    _chain_graph("Daily EP Scan", "ep", "paste"),
]


async def seed_default_definitions(repo: Any) -> int:
    """Seed the three presets if absent (matched by name). Returns count created."""
    existing = {d["name"] for d in await repo.list_definitions()}
    created = 0
    for preset in PRESET_DEFINITIONS:
        if preset["name"] in existing:
            continue
        await repo.create_definition(str(uuid.uuid4()), preset["name"], preset)
        created += 1
    if created:
        logger.info("seeded %d default pipeline definition(s)", created)
    return created
