"""In-memory Repo fake for route tests (no Postgres)."""

from __future__ import annotations

from typing import Any, Optional


class FakeRepo:
    """Duck-types ``app.db.Repo`` for hermetic route tests."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.artifacts: dict[str, dict[str, Any]] = {}

    async def create_run(
        self,
        run_id: str,
        name: str,
        pipeline_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        run = {
            "id": run_id,
            "name": name,
            "pipeline_type": pipeline_type,
            "status": "queued",
            "params": params,
            "counts": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        self.runs[run_id] = run
        return dict(run)

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        run = self.runs.get(run_id)
        return dict(run) if run else None

    async def list_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        return [dict(r) for r in list(self.runs.values())[:limit]]

    async def set_status(
        self,
        run_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        counts: Optional[dict[str, Any]] = None,
    ) -> None:
        run = self.runs[run_id]
        run["status"] = status
        if error is not None:
            run["error"] = error
        if counts is not None:
            run["counts"] = counts

    async def upsert_artifact(self, run_id: str, stage: str, payload: Any) -> None:
        self.artifacts.setdefault(run_id, {})[stage] = payload

    async def get_artifacts(self, run_id: str) -> dict[str, Any]:
        return dict(self.artifacts.get(run_id, {}))
