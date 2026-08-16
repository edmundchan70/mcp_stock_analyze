"""Tool registry — ``@register("id")`` fills ``REGISTRY``; ``get_tools()`` serves it.

Built-ins live in :mod:`stock_analyze.tools.builtins` (imported from the
package ``__init__`` so every ``from stock_analyze.tools import get_tools``
sees the full palette). Custom tools can ``register`` from anywhere; the
server imports + validates the whole registry at startup (T21).
"""

from __future__ import annotations

from typing import Any, Optional

from .protocol import PORT_STAGES, PortStage, ToolSpec, stage_accepts

REGISTRY: dict[str, ToolSpec] = {}

_HARD_FAILURE_FIELDS = (
    "family",
    "select",
    "limit",
    "apply_gates",
    "run_catalyst",
    "bo_profile",
    "scan_id",
    "report_format",
    "min_rating",
)


def register(tool_id: str):
    """Register a :class:`ToolSpec` under ``tool_id``."""

    def decorator(spec: ToolSpec) -> ToolSpec:
        if tool_id in REGISTRY and REGISTRY[tool_id] is not spec:
            raise ValueError(f"duplicate tool id: {tool_id}")
        if spec.id != tool_id:
            raise ValueError(f"tool id mismatch: {spec.id!r} != {tool_id!r}")
        REGISTRY[tool_id] = spec
        return spec

    return decorator


def get_tools() -> list[ToolSpec]:
    """All registered tools, stable-ordered by phase then id."""
    return sorted(REGISTRY.values(), key=lambda t: (t.phase, t.id))


def get_tool(tool_id: str) -> Optional[ToolSpec]:
    return REGISTRY.get(tool_id)


def validate_registry() -> list[str]:
    """Validate every registered ToolSpec; return a list of error strings."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    for spec in get_tools():
        if spec.id in seen_ids:
            errors.append(f"tool {spec.id!r}: duplicate id")
        seen_ids.add(spec.id)

        if spec.phase not in (1, 2, 3, 4):
            errors.append(f"tool {spec.id!r}: invalid phase {spec.phase!r}")

        if spec.callable is None:
            errors.append(f"tool {spec.id!r}: missing callable")

        if not spec.outputs:
            errors.append(f"tool {spec.id!r}: no output ports")

        for port in list(spec.inputs) + list(spec.outputs):
            if port.type not in PORT_STAGES:
                errors.append(
                    f"tool {spec.id!r}: port {port.id!r} has non-canonical "
                    f"stage {port.type!r} (v1 allows the 5 canonical stages only)"
                )
            if not port.required and spec.phase >= 1:
                pass  # optional ports are fine on any tool

        for var in spec.variables:
            if var.kind not in ("number", "boolean", "select", "text"):
                errors.append(
                    f"tool {spec.id!r}: variable {var.key!r} has invalid kind {var.kind!r}"
                )
            if var.kind == "select" and not var.options:
                errors.append(
                    f"tool {spec.id!r}: select variable {var.key!r} needs options"
                )
            if var.key in _HARD_FAILURE_FIELDS and var.kind not in ("select", "number", "boolean"):
                errors.append(
                    f"tool {spec.id!r}: hard-failure variable {var.key!r} must be "
                    f"select/number/boolean"
                )

    return errors


def registry_payload() -> list[dict[str, Any]]:
    """JSON-safe list for ``GET /api/tools``."""
    return [spec.to_dict() for spec in get_tools()]


__all__ = [
    "REGISTRY",
    "get_tool",
    "get_tools",
    "register",
    "registry_payload",
    "validate_registry",
]
