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


@pytest.mark.asyncio
async def test_scan_signals_record_and_streaks():
    from app.db import connect_repo

    url = os.environ["TEST_DATABASE_URL"]
    repo = await connect_repo(url)
    try:
        await repo.record_scan_signals(["AAPL", "MSFT"], "zhao", "daily", signal_date="2026-08-06")
        await repo.record_scan_signals(["AAPL"], "zhao", "daily", signal_date="2026-08-07")
        await repo.record_scan_signals(["AAPL", "MSFT"], "zhao", "daily", signal_date="2026-08-08")

        # Prior-to-as_of streaks: as_of 2026-08-09 counts the 3 prior days.
        streaks = await repo.get_scan_streaks(["AAPL", "MSFT", "TSLA"], "zhao", "daily", as_of="2026-08-09")
        assert streaks["AAPL"] == 3
        assert streaks["MSFT"] == 2   # 08-06, 08-08 — broken by 08-07
        assert "TSLA" not in streaks

        # as_of 2026-08-08 excludes today's row → prior = 2.
        prior = await repo.get_scan_streaks(["AAPL"], "zhao", "daily", as_of="2026-08-08")
        assert prior["AAPL"] == 2

        # Re-recording the same day is idempotent.
        written = await repo.record_scan_signals(["AAPL"], "zhao", "daily", signal_date="2026-08-08")
        assert written == 0
    finally:
        await repo.pool.close()
