"""Runs API: create/list/get a run and stream its progress over SSE."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from stock_analyze.force_include import parse_force_include_text
from stock_analyze.tools import REGISTRY
from stock_analyze.tools.canvas import to_walker_definition, validate_canvas_graph
from stock_analyze.tools.preview import estimate_graph_run, estimate_symbol_count

from ..config import get_output_root
from ..db import Repo
from ..jobs import JobManager
from ..schemas import RunCreate

router = APIRouter(prefix="/api")


def _get_repo(request: Request) -> Repo:
    return request.app.state.repo


def _get_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


async def _resolve_run_graph(body: RunCreate, repo: Repo) -> dict:
    """Fetch/validate the canvas graph for a graph run; 404/422 on problems."""
    if body.graph is None and body.definition_id is None:
        return {}
    if body.graph is not None:
        graph = body.graph
    else:
        definition = await repo.get_definition(body.definition_id)
        if definition is None:
            raise HTTPException(status_code=404, detail="definition not found")
        graph = definition["graph"]
    errors = validate_canvas_graph(graph, tools=REGISTRY)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return graph


def _terminal_event(run: dict) -> dict:
    if run.get("status") == "failed":
        return {"type": "failed", "error": run.get("error")}
    return {
        "type": "done",
        "counts": run.get("counts"),
        "steps_completed": run.get("params", {}).get("steps_completed"),
    }


async def _event_stream(
    run_id: str,
    repo: Repo,
    manager: JobManager,
    initial_run: dict,
) -> AsyncGenerator[str, None]:
    # Already terminal — replay a single terminal event from the DB.
    if initial_run["status"] in ("succeeded", "failed"):
        payload = _terminal_event(initial_run)
        if initial_run["status"] == "succeeded":
            artifacts = await repo.get_artifacts(run_id)
            if artifacts.get("merge_table"):
                payload["merge_table"] = artifacts["merge_table"]
        yield _format_sse("done" if initial_run["status"] == "succeeded" else "failed", payload)
        return

    queue = manager.queue_for(run_id)
    if queue is None:
        # Started before this process' registry had it (e.g. a queued row with no
        # live job). Emit queued and return.
        yield _format_sse("progress", {"type": "queued", "run_id": run_id})
        return

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=15.0)
        except asyncio.TimeoutError:
            yield ": keep-alive\n\n"
            continue

        if event.get("type") in ("done", "failed"):
            yield _format_sse(event["type"], event)
            break
        yield _format_sse("progress", event)


def _format_sse(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


@router.post("/runs", status_code=201)
async def create_run(body: RunCreate, request: Request) -> dict:
    repo = _get_repo(request)
    manager = _get_manager(request)

    graph = await _resolve_run_graph(body, repo)
    params = body.model_dump()
    params["output_root"] = get_output_root()
    if graph:
        params["graph"] = graph

    run_id = str(uuid.uuid4())
    run = await repo.create_run(
        run_id,
        body.name,
        body.pipeline_type,
        params,
        definition_id=body.definition_id,
        graph_snapshot=graph or None,
    )
    manager.start(run_id, params, repo, asyncio.get_running_loop())
    return run


@router.post("/runs/preview")
async def preview_run(body: RunCreate, request: Request) -> dict:
    """Estimate cost + duration of a run before executing it (T22)."""
    repo = _get_repo(request)
    graph = await _resolve_run_graph(body, repo)

    if graph:
        definition = to_walker_definition(graph)
        if body.universe_source == "snapshot":
            symbol_count = estimate_symbol_count({"source": "snapshot"})
        else:
            parsed = parse_force_include_text(body.force_symbols)
            symbol_count = max(1, len(parsed.symbols))
        estimate = estimate_graph_run(definition, symbol_count)
        return {
            "estimate": estimate,
            "graph": {
                "name": definition.get("name"),
                "nodes": len(definition.get("nodes") or []),
                "edges": len(definition.get("edges") or []),
            },
        }

    # Legacy pipeline preview: advisory symbol-count-only estimate.
    if body.use_screener:
        symbol_count = estimate_symbol_count({"source": "snapshot"})
    else:
        parsed = parse_force_include_text(body.force_symbols)
        symbol_count = max(1, len(parsed.symbols))
    return {
        "estimate": {
            "symbols": symbol_count,
            "seconds": round(symbol_count * 0.06, 1),
            "duration": f"{symbol_count * 0.06 / 60:.1f}m",
            "cost": round(symbol_count * 0.00015, 2),
            "nodes": [],
            "warnings": [],
        },
        "graph": {"name": body.name, "nodes": 0, "edges": 0},
    }


@router.get("/runs")
async def list_runs(request: Request) -> dict:
    repo = _get_repo(request)
    return {"runs": await repo.list_runs()}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict:
    repo = _get_repo(request)
    run = await repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    run["artifacts"] = await repo.get_artifacts(run_id)
    return run


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    repo = _get_repo(request)
    manager = _get_manager(request)
    run = await repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return StreamingResponse(
        _event_stream(run_id, repo, manager, run),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
