"""Real-Postgres integration tests (skipped unless TEST_DATABASE_URL is set)."""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — set it to a disposable Postgres URL to run DB tests",
)


@pytest.mark.asyncio
async def test_bootstrap_and_roundtrip():
    from app.db import connect_repo

    url = os.environ["TEST_DATABASE_URL"]

    # Bootstrap twice to prove idempotency (CREATE ... IF NOT EXISTS).
    repo = await connect_repo(url)
    repo2 = await connect_repo(url)
    await repo2.pool.close()

    try:
        run_id = str(uuid.uuid4())
        await repo.create_run(run_id, "nightly", "daily_bo_scan", {"force_symbols": "AAPL"})
        assert (await repo.get_run(run_id))["status"] == "queued"

        await repo.set_status(run_id, "succeeded", counts={"5": 1, "4": 0, "3": 0})
        await repo.upsert_artifact(run_id, "agent1", {"ratings": [1]})
        await repo.upsert_artifact(run_id, "agent1", {"ratings": [1, 2]})  # upsert, not duplicate

        run = await repo.get_run(run_id)
        assert run["status"] == "succeeded"
        assert run["counts"] == {"5": 1, "4": 0, "3": 0}

        artifacts = await repo.get_artifacts(run_id)
        assert artifacts["agent1"] == {"ratings": [1, 2]}

        runs = await repo.list_runs()
        assert any(r["id"] == run_id for r in runs)
    finally:
        await repo.pool.close()
