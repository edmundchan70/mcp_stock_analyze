"""RunControl unit tests + control endpoint integration tests."""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest

from app.control import RunControl
from app.main import create_app
from fakes import FakeRepo
from stock_analyze.tools.control import RunCancelled


# ── RunControl unit tests ─────────────────────────────────────────────


def test_skip_arm_and_query():
    c = RunControl()
    assert not c.is_skipped("sr_1")
    c.arm_skip("sr_1")
    assert c.is_skipped("sr_1")
    assert c.skipped_nodes() == ["sr_1"]


def test_pause_resume():
    c = RunControl()
    assert not c.is_paused()
    c.pause()
    assert c.is_paused()
    c.resume()
    assert not c.is_paused()


def test_checkpoint_raises_when_cancelled():
    c = RunControl()
    c.cancel()
    with pytest.raises(RunCancelled):
        c.checkpoint()


def test_checkpoint_blocks_while_paused_then_resumes():
    c = RunControl()
    c.pause()
    result = {"done": False}

    def worker():
        c.checkpoint()
        result["done"] = True

    t = threading.Thread(target=worker)
    t.start()
    # give the worker time to reach the blocking checkpoint
    t.join(timeout=0.2)
    assert result["done"] is False
    c.resume()
    t.join(timeout=1.0)
    assert result["done"] is True


def test_confirmation_roundtrip():
    c = RunControl()
    c.request_confirmation("sr_1", 60, 120)
    pending = c.pending_confirmation()
    assert pending == {"node_id": "sr_1", "symbol_count": 60, "tavily_estimate": 120}

    c.confirm("sr_1", "proceed")
    assert c.pending_confirmation() is None


def test_cancel_resolves_pending_confirmation():
    c = RunControl()
    c.request_confirmation("sr_1", 60, 120)

    decision = {"value": None}

    def waiter():
        decision["value"] = c.wait_confirmation("sr_1")

    t = threading.Thread(target=waiter)
    t.start()
    t.join(timeout=0.2)
    assert decision["value"] is None  # still blocked

    c.cancel()
    t.join(timeout=1.0)
    assert decision["value"] == "cancel"


# ── control endpoint integration ──────────────────────────────────────


def _running_app(control: RunControl, run_id: str = "r1"):
    repo = FakeRepo()
    app = create_app(repo=repo)
    manager = app.state.job_manager
    manager._controls[run_id] = control
    manager._queues[run_id] = asyncio.Queue()
    return app, repo, manager


@pytest.mark.asyncio
async def test_control_skip_pause_resume_confirm():
    control = RunControl()
    app, repo, manager = _running_app(control)
    await repo.create_run("r1", "g", "daily_bo_scan", {"graph": {}})
    await repo.set_status("r1", "running")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/runs/r1/control", json={"action": "skip", "node_id": "sr_1"})
        assert r.status_code == 200
        assert control.is_skipped("sr_1")

        r = await client.post("/api/runs/r1/control", json={"action": "pause"})
        assert r.status_code == 200
        assert control.is_paused()

        r = await client.post("/api/runs/r1/control", json={"action": "resume"})
        assert r.status_code == 200
        assert not control.is_paused()

        control.request_confirmation("sr_1", 60, 120)
        r = await client.post(
            "/api/runs/r1/control", json={"action": "confirm", "node_id": "sr_1", "decision": "proceed"}
        )
        assert r.status_code == 200
        assert control.pending_confirmation() is None


@pytest.mark.asyncio
async def test_control_cancel_sets_cancelled_flag():
    control = RunControl()
    app, repo, _ = _running_app(control)
    await repo.create_run("r1", "g", "daily_bo_scan", {"graph": {}})
    await repo.set_status("r1", "running")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/runs/r1/control", json={"action": "cancel"})
        assert r.status_code == 200
        assert control.cancelled is True


@pytest.mark.asyncio
async def test_control_validation_errors():
    control = RunControl()
    app, repo, _ = _running_app(control)
    await repo.create_run("r1", "g", "daily_bo_scan", {"graph": {}})
    await repo.set_status("r1", "running")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # skip requires node_id
        r = await client.post("/api/runs/r1/control", json={"action": "skip"})
        assert r.status_code == 422
        # confirm requires decision
        r = await client.post("/api/runs/r1/control", json={"action": "confirm", "node_id": "sr_1"})
        assert r.status_code == 422
        # unknown action
        r = await client.post("/api/runs/r1/control", json={"action": "explode"})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_control_unknown_and_finished_runs_rejected():
    control = RunControl()
    app, repo, _ = _running_app(control)
    await repo.create_run("r1", "g", "daily_bo_scan", {"graph": {}})
    await repo.set_status("r1", "succeeded")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/runs/nope/control", json={"action": "cancel"})
        assert r.status_code == 404

        r = await client.post("/api/runs/r1/control", json={"action": "cancel"})
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_control_on_non_graph_run_rejected():
    control = RunControl()
    app, repo, _ = _running_app(control, run_id="r1")
    await repo.create_run("r2", "legacy", "daily_bo_scan", {"pipeline_type": "daily_bo_scan"})
    await repo.set_status("r2", "running")
    # no control registered for r2

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/runs/r2/control", json={"action": "cancel"})
        assert r.status_code == 409
