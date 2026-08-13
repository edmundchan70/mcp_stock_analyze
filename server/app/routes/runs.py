"""Runs API: create/list/get a run and stream its progress over SSE."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..config import get_output_root
from ..db import Repo
from ..jobs import JobManager
from ..schemas import RunCreate

router = APIRouter(prefix="/api")


def _get_repo(request: Request) -> Repo:
    return request.app.state.repo


def _get_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


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
        yield _format_sse("done" if initial_run["status"] == "succeeded" else "failed", _terminal_event(initial_run))
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

    params = body.model_dump()
    params["output_root"] = get_output_root()

    run_id = str(uuid.uuid4())
    run = await repo.create_run(run_id, body.name, body.pipeline_type, params)
    manager.start(run_id, params, repo, asyncio.get_running_loop())
    return run


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
