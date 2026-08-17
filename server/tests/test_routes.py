"""Route tests using an in-memory repo and a patched run_daily (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.jobs import JobManager
from app.main import create_app
from app.routes.runs import _event_stream
from fakes import FakeRepo
from stock_analyze.pipeline import RunResult


def _write_fixture_run_dir(tmp_path, name: str = "nightly") -> tuple:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_meta.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    (run_dir / f"{name}_agent1.json").write_text(
        json.dumps({"counts": {"5": 1, "4": 2, "3": 3}}), encoding="utf-8"
    )
    (run_dir / f"{name}_agent3.json").write_text(
        json.dumps({"count": 3, "stocks": [{"symbol": "AAPL", "final_rating": 5}]}),
        encoding="utf-8",
    )
    return run_dir


@pytest.mark.asyncio
async def test_create_run_and_poll(monkeypatch, tmp_path):
    run_dir = _write_fixture_run_dir(tmp_path)
    monkeypatch.setattr(
        "app.jobs.run_daily",
        lambda config, reporter=None: RunResult(0, run_dir, ["agent1", "agent3"]),
    )

    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/runs",
            json={"name": "nightly", "pipeline_type": "daily_bo_scan", "force_symbols": "AAPL"},
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        await app.state.job_manager.tasks[run_id]  # wait for the job to finish

        detail = await client.get(f"/api/runs/{run_id}")
        assert detail.status_code == 200
        data = detail.json()
        assert data["status"] == "succeeded"
        assert data["counts"] == {"5": 1, "4": 2, "3": 3}
        assert "agent1" in data["artifacts"]
        assert "agent3" in data["artifacts"]


@pytest.mark.asyncio
async def test_create_run_validation():
    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        empty = await client.post(
            "/api/runs",
            json={"pipeline_type": "daily_bo_scan", "force_symbols": ""},
        )
        assert empty.status_code == 422

        unknown = await client.post(
            "/api/runs",
            json={"pipeline_type": "daily_unknown", "force_symbols": "AAPL"},
        )
        assert unknown.status_code == 422


@pytest.mark.asyncio
async def test_create_run_sweep_no_symbols(monkeypatch, tmp_path):
    """use_screener=True allows an empty force_symbols (market sweep)."""
    run_dir = _write_fixture_run_dir(tmp_path)
    monkeypatch.setattr(
        "app.jobs.run_daily",
        lambda config, reporter=None: RunResult(0, run_dir, ["agent1", "agent3"]),
    )

    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/runs",
            json={"name": "sweep", "pipeline_type": "daily_bo_scan", "use_screener": True, "force_symbols": ""},
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]
        await app.state.job_manager.tasks[run_id]

        detail = await client.get(f"/api/runs/{run_id}")
        assert detail.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_list_and_get_404():
    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listing = await client.get("/api/runs")
        assert listing.status_code == 200
        assert listing.json() == {"runs": []}

        missing = await client.get("/api/runs/does-not-exist")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_health():
    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_event_stream_terminal_replay():
    repo = FakeRepo()
    repo.runs["abc"] = {
        "id": "abc",
        "name": "nightly",
        "pipeline_type": "daily_bo_scan",
        "status": "succeeded",
        "counts": {"5": 1},
        "error": None,
        "params": {},
        "started_at": None,
        "finished_at": None,
    }
    chunks = []
    async for chunk in _event_stream("abc", repo, JobManager(), repo.runs["abc"]):
        chunks.append(chunk)
    body = "".join(chunks)
    assert "event: done" in body


@pytest.mark.asyncio
async def test_run_failure_persists_error(monkeypatch, tmp_path):
    def boom(config, reporter=None):
        raise RuntimeError("scan blew up")

    monkeypatch.setattr("app.jobs.run_daily", boom)
    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/runs",
            json={"name": "x", "pipeline_type": "daily_bo_scan", "force_symbols": "AAPL"},
        )
        run_id = resp.json()["id"]
        await app.state.job_manager.tasks[run_id]
        detail = await client.get(f"/api/runs/{run_id}")
        assert detail.json()["status"] == "failed"
        assert "scan blew up" in detail.json()["error"]
