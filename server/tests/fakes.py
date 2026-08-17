"""In-memory Repo fake for route tests (no Postgres)."""

from __future__ import annotations

from typing import Any, Optional


class FakeRepo:
    """Duck-types ``app.db.Repo`` for hermetic route tests."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.definitions: dict[str, dict[str, Any]] = {}
        self.component_templates: dict[str, dict[str, Any]] = {}

    async def create_run(
        self,
        run_id: str,
        name: str,
        pipeline_type: str,
        params: dict[str, Any],
        *,
        definition_id: Optional[str] = None,
        graph_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        run = {
            "id": run_id,
            "name": name,
            "pipeline_type": pipeline_type,
            "status": "queued",
            "params": params,
            "counts": None,
            "error": None,
            "definition_id": definition_id,
            "graph_snapshot": graph_snapshot,
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

    async def mark_interrupted_runs(self) -> int:
        count = 0
        for run in self.runs.values():
            if run["status"] in ("queued", "running"):
                run["status"] = "failed"
                run["error"] = "server restarted — run interrupted"
                count += 1
        return count

    async def upsert_artifact(self, run_id: str, stage: str, payload: Any) -> None:
        self.artifacts.setdefault(run_id, {})[stage] = payload

    async def get_artifacts(self, run_id: str) -> dict[str, Any]:
        return dict(self.artifacts.get(run_id, {}))

    # ── pipeline definitions ─────────────────────────────────────────

    async def list_definitions(self, limit: int = 200) -> list[dict[str, Any]]:
        return [dict(d) for d in list(self.definitions.values())[:limit]]

    async def get_definition(self, definition_id: str) -> Optional[dict[str, Any]]:
        d = self.definitions.get(definition_id)
        return dict(d) if d else None

    async def create_definition(
        self, definition_id: str, name: str, graph: dict[str, Any]
    ) -> dict[str, Any]:
        d = {"id": definition_id, "name": name, "graph": graph, "created_at": None, "updated_at": None}
        self.definitions[definition_id] = d
        return dict(d)

    async def update_definition(
        self, definition_id: str, name: str, graph: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        d = self.definitions.get(definition_id)
        if d is None:
            return None
        d.update({"name": name, "graph": graph})
        return dict(d)

    async def delete_definition(self, definition_id: str) -> bool:
        return self.definitions.pop(definition_id, None) is not None

    # ── component templates ──────────────────────────────────────────

    async def list_component_templates(self, limit: int = 200) -> list[dict[str, Any]]:
        return [dict(t) for t in list(self.component_templates.values())[:limit]]

    async def get_component_template(self, template_id: str) -> Optional[dict[str, Any]]:
        t = self.component_templates.get(template_id)
        return dict(t) if t else None

    async def create_component_template(
        self,
        template_id: str,
        name: str,
        component_id: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        t = {
            "id": template_id,
            "name": name,
            "component_id": component_id,
            "variables": variables,
            "created_at": None,
            "updated_at": None,
        }
        self.component_templates[template_id] = t
        return dict(t)

    async def update_component_template(
        self,
        template_id: str,
        name: str,
        component_id: str,
        variables: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        t = self.component_templates.get(template_id)
        if t is None:
            return None
        t.update({"name": name, "component_id": component_id, "variables": variables})
        return dict(t)

    async def delete_component_template(self, template_id: str) -> bool:
        return self.component_templates.pop(template_id, None) is not None
