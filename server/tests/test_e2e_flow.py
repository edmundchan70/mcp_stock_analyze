"""End-to-end flow with a mocked run_daily that exercises the reporter duck-type.

This is the guard proving the EventReporter adapter matches the pipeline's
RunProgress contract end-to-end: reporter events flow into the queue and the
artifacts written by a (mocked) run are persisted to the repo.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from fakes import FakeRepo
from stock_analyze.pipeline import RunResult


def _fake_run_daily(config, reporter=None):
    """Mimic the pipeline's reporter calls, then write artifacts like run_daily does."""
    reporter.stage("Agent 1 — running BO scan")
    reporter.begin_ticker(2, "Resolving symbols", throttle=1)
    reporter.ticker(1, 2, "AAPL", "resolving")
    reporter.ticker(2, 2, "MSFT", "resolving")
    reporter.end_ticker()
    reporter.stage_done("Agent 1 done")
    reporter.console.print("funnel table")

    run_dir = Path(tempfile.mkdtemp())
    (run_dir / "run_meta.json").write_text(json.dumps({"name": config.name}), encoding="utf-8")
    (run_dir / f"{config.name}_agent1.json").write_text(
        json.dumps({"counts": {"5": 1, "4": 0, "3": 0}}), encoding="utf-8"
    )
    (run_dir / f"{config.name}_agent3.json").write_text(
        json.dumps({"count": 1, "stocks": [{"symbol": "AAPL", "final_rating": 5}]}),
        encoding="utf-8",
    )
    return RunResult(0, run_dir, ["agent1", "agent3"])


@pytest.mark.asyncio
async def test_mocked_e2e_flow(monkeypatch):
    monkeypatch.setattr("app.jobs.run_daily", _fake_run_daily)

    app = create_app(repo=FakeRepo())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/runs",
            json={"name": "nightly", "pipeline_type": "daily_bo_scan", "force_symbols": "AAPL, MSFT"},
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        await app.state.job_manager.tasks[run_id]

        # Reporter events flowed into the queue and terminated with "done".
        queue = app.state.job_manager.queue_for(run_id)
        event_types = []
        while not queue.empty():
            event_types.append(queue.get_nowait()["type"])
        assert "stage" in event_types
        assert "ticker_begin" in event_types
        assert "ticker" in event_types
        assert "ticker_end" in event_types
        assert "console" in event_types
        assert event_types[-1] == "done"

        detail = await client.get(f"/api/runs/{run_id}")
        data = detail.json()
        assert data["status"] == "succeeded"
        assert data["counts"] == {"5": 1, "4": 0, "3": 0}
        assert "agent1" in data["artifacts"]
        assert "agent3" in data["artifacts"]
