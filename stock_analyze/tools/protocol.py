"""Component graph tool protocol — the ToolSpec registry model (T13).

A Tool is one palette component: Scanner, Quant Filter/Gate, AI Search, Report
(or a registered custom tool). Tools communicate in *rows* keyed by SymbolKey
``{symbol, exchange}`` plus opaque extra columns, typed by 5 canonical port
stages (T11). ``INPUT_ACCEPTS`` is the port-stage assignability matrix and is
the canonical source for both server graph validation and the canvas
``isValidConnection``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

# ── canonical port stages (T11) ────────────────────────────────────

PortStage = Literal[
    "symbolkey",
    "scan_rows",
    "filtered_rows",
    "enriched_rows",
    "report_rows",
]

PORT_STAGES: tuple[str, ...] = (
    "symbolkey",
    "scan_rows",
    "filtered_rows",
    "enriched_rows",
    "report_rows",
)

# Progressive accept chain: an input port of stage X accepts rows from any
# source stage in its accept set. Relaxed ordering keeps skip edges legal
# (Scanner → Report) while remaining a DAG (row types only advance).
INPUT_ACCEPTS: dict[str, tuple[str, ...]] = {
    "symbolkey": ("symbolkey",),
    "scan_rows": ("scan_rows",),
    "filtered_rows": ("scan_rows", "filtered_rows"),
    "enriched_rows": ("scan_rows", "filtered_rows", "enriched_rows"),
    "report_rows": ("scan_rows", "filtered_rows", "enriched_rows"),
}


def stage_accepts(target_stage: str, source_stage: str) -> bool:
    """True when a wire from ``source_stage`` to ``target_stage`` is legal."""
    return source_stage in INPUT_ACCEPTS.get(target_stage, ())


# Marker key on a soft-fail (degraded) row: the walker drops such rows from
# the forward stream and records them on the node result instead (T19).
ERROR_KEY = "_error"


# ── port + variable definitions ────────────────────────────────────


@dataclass(frozen=True)
class PortDef:
    """A typed input/output port on a Tool."""

    id: str
    type: PortStage
    required: bool
    label: str = ""


VarKind = Literal["number", "boolean", "select", "text"]
VarValue = str | int | float | bool


@dataclass(frozen=True)
class VariableDef:
    """One editable inspector field (the stub's VariableDef shape)."""

    key: str
    label: str
    kind: VarKind
    default: VarValue
    group: str
    options: Optional[list[str]] = None


ToolInputs = dict[str, list[dict[str, Any]]]
ToolCallable = Callable[[ToolInputs, dict[str, Any]], list[dict[str, Any]]]


@dataclass
class ToolSpec:
    """A registered graph component.

    ``callable`` is ``(inputs: dict[port_id, list[row]], params: dict) ->
    list[row]``. Rows are ``{symbol, exchange, ...opaque}``; a ``report_rows``
    output must carry a numeric rating. The callable is validated at server
    startup and must be JSON-safe at the boundary (no Pydantic models out).
    """

    id: str
    name: str
    description: str
    phase: int  # 1..4 — palette grouping only
    inputs: list[PortDef] = field(default_factory=list)
    outputs: list[PortDef] = field(default_factory=list)
    variables: list[VariableDef] = field(default_factory=list)
    callable: Optional[ToolCallable] = None

    def input(self, port_id: str) -> Optional[PortDef]:
        return next((p for p in self.inputs if p.id == port_id), None)

    def output(self, port_id: str) -> Optional[PortDef]:
        return next((p for p in self.outputs if p.id == port_id), None)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe registry payload served by ``GET /api/tools``."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "phase": self.phase,
            "inputs": [p.__dict__ for p in self.inputs],
            "outputs": [p.__dict__ for p in self.outputs],
            "variables": [v.__dict__ for v in self.variables],
        }


__all__ = [
    "ERROR_KEY",
    "INPUT_ACCEPTS",
    "PORT_STAGES",
    "PortDef",
    "PortStage",
    "ToolCallable",
    "ToolInputs",
    "ToolSpec",
    "VarKind",
    "VarValue",
    "VariableDef",
    "stage_accepts",
]
