"""Postgres access layer: asyncpg pool + schema bootstrap + run/artifact queries."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _dump(value: Any) -> Optional[str]:
    """Encode a dict/list for a JSONB column (asyncpg accepts str)."""
    if value is None:
        return None
    return json.dumps(value)


def _load(value: Any) -> Any:
    """Decode a JSONB column (asyncpg may return str or an already-decoded object)."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _run_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "pipeline_type": row["pipeline_type"],
        "status": row["status"],
        "params": _load(row["params"]),
        "counts": _load(row["counts"]),
        "error": row["error"],
        "definition_id": str(row["definition_id"]) if row["definition_id"] else None,
        "graph_snapshot": _load(row["graph_snapshot"]),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
    }


def _definition_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "graph": _load(row["graph"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _template_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "component_id": row["component_id"],
        "variables": _load(row["variables"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


class Repo:
    """Repository of runs and their per-stage JSON artifacts."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

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
        row = await self.pool.fetchrow(
            """
            INSERT INTO runs (id, name, pipeline_type, status, params, definition_id, graph_snapshot)
            VALUES ($1, $2, $3, 'queued', $4, $5, $6)
            RETURNING *
            """,
            run_id,
            name,
            pipeline_type,
            _dump(params),
            definition_id,
            _dump(graph_snapshot),
        )
        return _run_to_dict(row)

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = await self.pool.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
        return _run_to_dict(row) if row else None

    async def list_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT $1", limit
        )
        return [_run_to_dict(r) for r in rows]

    async def set_status(
        self,
        run_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        counts: Optional[dict[str, Any]] = None,
    ) -> None:
        await self.pool.execute(
            """
            UPDATE runs
            SET status = $2,
                error = $3,
                counts = COALESCE($4, counts),
                finished_at = CASE
                    WHEN $2 IN ('succeeded', 'failed', 'cancelled') THEN now()
                    ELSE finished_at
                END
            WHERE id = $1
            """,
            run_id,
            status,
            error,
            _dump(counts),
        )

    async def mark_interrupted_runs(self) -> int:
        """Mark orphaned ``queued``/``running`` rows as failed (server restart)."""
        tag = await self.pool.execute(
            """
            UPDATE runs
            SET status = 'failed',
                error = 'server restarted — run interrupted',
                finished_at = now()
            WHERE status IN ('queued', 'running')
            """
        )
        try:
            return int(str(tag).split()[-1])
        except (ValueError, IndexError):
            return 0

    async def upsert_artifact(self, run_id: str, stage: str, payload: Any) -> None:
        await self.pool.execute(
            """
            INSERT INTO run_artifacts (run_id, stage, payload)
            VALUES ($1, $2, $3)
            ON CONFLICT (run_id, stage)
            DO UPDATE SET payload = EXCLUDED.payload, created_at = now()
            """,
            run_id,
            stage,
            _dump(payload),
        )

    async def get_artifacts(self, run_id: str) -> dict[str, Any]:
        rows = await self.pool.fetch(
            "SELECT stage, payload FROM run_artifacts WHERE run_id = $1", run_id
        )
        return {r["stage"]: _load(r["payload"]) for r in rows}

    # ── pipeline definitions ─────────────────────────────────────────

    async def list_definitions(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT * FROM pipeline_definitions ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        return [_definition_to_dict(r) for r in rows]

    async def get_definition(self, definition_id: str) -> Optional[dict[str, Any]]:
        row = await self.pool.fetchrow(
            "SELECT * FROM pipeline_definitions WHERE id = $1", definition_id
        )
        return _definition_to_dict(row) if row else None

    async def create_definition(
        self, definition_id: str, name: str, graph: dict[str, Any]
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            """
            INSERT INTO pipeline_definitions (id, name, graph)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            definition_id,
            name,
            _dump(graph),
        )
        return _definition_to_dict(row)

    async def update_definition(
        self, definition_id: str, name: str, graph: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        row = await self.pool.fetchrow(
            """
            UPDATE pipeline_definitions
            SET name = $2, graph = $3, updated_at = now()
            WHERE id = $1
            RETURNING *
            """,
            definition_id,
            name,
            _dump(graph),
        )
        return _definition_to_dict(row) if row else None

    async def delete_definition(self, definition_id: str) -> bool:
        result = await self.pool.execute(
            "DELETE FROM pipeline_definitions WHERE id = $1", definition_id
        )
        return result == "DELETE 1"

    # ── component templates ──────────────────────────────────────────

    async def list_component_templates(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT * FROM component_templates ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        return [_template_to_dict(r) for r in rows]

    async def get_component_template(self, template_id: str) -> Optional[dict[str, Any]]:
        row = await self.pool.fetchrow(
            "SELECT * FROM component_templates WHERE id = $1", template_id
        )
        return _template_to_dict(row) if row else None

    async def create_component_template(
        self,
        template_id: str,
        name: str,
        component_id: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            """
            INSERT INTO component_templates (id, name, component_id, variables)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            template_id,
            name,
            component_id,
            _dump(variables),
        )
        return _template_to_dict(row)

    async def update_component_template(
        self,
        template_id: str,
        name: str,
        component_id: str,
        variables: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        row = await self.pool.fetchrow(
            """
            UPDATE component_templates
            SET name = $2, component_id = $3, variables = $4, updated_at = now()
            WHERE id = $1
            RETURNING *
            """,
            template_id,
            name,
            component_id,
            _dump(variables),
        )
        return _template_to_dict(row) if row else None

    async def delete_component_template(self, template_id: str) -> bool:
        result = await self.pool.execute(
            "DELETE FROM component_templates WHERE id = $1", template_id
        )
        return result == "DELETE 1"


async def connect_repo(database_url: str) -> Repo:
    """Create a pool, bootstrap the schema, and return a Repo."""
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(schema)
    return Repo(pool)


async def close_repo(repo: Repo) -> None:
    await repo.pool.close()
