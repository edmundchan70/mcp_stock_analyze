"""Definitions + component templates API (T20/T25).

Stores canvas-shaped graph JSON in ``pipeline_definitions`` and reusable
component variable sets in ``component_templates``. Definitions are
validated against the tool registry on write.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from stock_analyze.tools import REGISTRY
from stock_analyze.tools.canvas import validate_canvas_graph

from ..db import Repo
from ..schemas import (
    ComponentTemplateCreate,
    ComponentTemplateUpdate,
    DefinitionCreate,
    DefinitionUpdate,
)

router = APIRouter(prefix="/api")


def _get_repo(request: Request) -> Repo:
    return request.app.state.repo


def _reject_invalid_graph(graph: dict[str, Any]) -> None:
    errors = validate_canvas_graph(graph, tools=REGISTRY)
    if errors:
        raise HTTPException(status_code=422, detail=errors)


# ── pipeline definitions ─────────────────────────────────────────────


@router.get("/definitions")
async def list_definitions(request: Request) -> dict:
    repo = _get_repo(request)
    return {"definitions": await repo.list_definitions()}


@router.post("/definitions", status_code=201)
async def create_definition(body: DefinitionCreate, request: Request) -> dict:
    repo = _get_repo(request)
    _reject_invalid_graph(body.graph)
    return await repo.create_definition(str(uuid.uuid4()), body.name, body.graph)


@router.get("/definitions/{definition_id}")
async def get_definition(definition_id: str, request: Request) -> dict:
    repo = _get_repo(request)
    definition = await repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="definition not found")
    return definition


@router.put("/definitions/{definition_id}")
async def update_definition(
    definition_id: str, body: DefinitionUpdate, request: Request
) -> dict:
    repo = _get_repo(request)
    _reject_invalid_graph(body.graph)
    definition = await repo.update_definition(definition_id, body.name, body.graph)
    if definition is None:
        raise HTTPException(status_code=404, detail="definition not found")
    return definition


@router.delete("/definitions/{definition_id}", status_code=204)
async def delete_definition(definition_id: str, request: Request) -> None:
    repo = _get_repo(request)
    if not await repo.delete_definition(definition_id):
        raise HTTPException(status_code=404, detail="definition not found")


# ── component templates ──────────────────────────────────────────────


def _reject_invalid_template(component_id: str) -> None:
    if component_id not in REGISTRY:
        raise HTTPException(status_code=422, detail=f"unknown component: {component_id}")


@router.get("/component-templates")
async def list_component_templates(request: Request) -> dict:
    repo = _get_repo(request)
    return {"templates": await repo.list_component_templates()}


@router.post("/component-templates", status_code=201)
async def create_component_template(
    body: ComponentTemplateCreate, request: Request
) -> dict:
    repo = _get_repo(request)
    _reject_invalid_template(body.component_id)
    return await repo.create_component_template(
        str(uuid.uuid4()), body.name, body.component_id, body.variables
    )


@router.get("/component-templates/{template_id}")
async def get_component_template(template_id: str, request: Request) -> dict:
    repo = _get_repo(request)
    template = await repo.get_component_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="component template not found")
    return template


@router.put("/component-templates/{template_id}")
async def update_component_template(
    template_id: str, body: ComponentTemplateUpdate, request: Request
) -> dict:
    repo = _get_repo(request)
    _reject_invalid_template(body.component_id)
    template = await repo.update_component_template(
        template_id, body.name, body.component_id, body.variables
    )
    if template is None:
        raise HTTPException(status_code=404, detail="component template not found")
    return template


@router.delete("/component-templates/{template_id}", status_code=204)
async def delete_component_template(template_id: str, request: Request) -> None:
    repo = _get_repo(request)
    if not await repo.delete_component_template(template_id):
        raise HTTPException(status_code=404, detail="component template not found")


__all__: list[Any] = []
