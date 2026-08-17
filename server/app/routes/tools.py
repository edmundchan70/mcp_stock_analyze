"""Tools API: serve the ToolSpec palette (T13)."""

from __future__ import annotations

from fastapi import APIRouter

from stock_analyze.tools import registry_payload, validate_registry

router = APIRouter(prefix="/api")


@router.get("/tools")
async def list_tools() -> dict:
    """Registered component palette (no callables — JSON-safe only)."""
    return {"tools": registry_payload()}


@router.get("/tools/validate")
async def validate_tools() -> dict:
    """Registry validation report (used by the editor health check)."""
    errors = validate_registry()
    return {"ok": not errors, "errors": errors}
