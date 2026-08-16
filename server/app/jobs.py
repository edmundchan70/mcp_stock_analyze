"""Background scan jobs: build RunConfig, run run_daily / component graphs, persist artifacts."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from stock_analyze.force_include import parse_force_include_text
from stock_analyze.pipeline import RunConfig, run_daily
from stock_analyze.tools import run_graph, validate_graph
from stock_analyze.tools.canvas import to_walker_definition

from .db import Repo
from .reporter import EventReporter

logger = logging.getLogger(__name__)

_ARTIFACT_STAGES = ("agent1", "agent2", "agent3")


def resolve_universe(params: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resolve the run universe into symbolkey rows + a walker universe config.

    ``paste`` parses ``force_symbols``; ``snapshot`` pulls the market-wide
    sweep (shared prefilter + market-cap resolution, family-agnostic).
    """
    source = params.get("universe_source", "paste")
    if source == "snapshot":
        from stock_analyze.data.polygon import (
            fetch_market_snapshot,
            prefilter_snapshot,
            resolve_market_caps,
        )

        snapshot = fetch_market_snapshot()
        prefiltered = prefilter_snapshot(snapshot)
        resolved = resolve_market_caps([r["symbol"] for r in prefiltered])
        rows = [
            {
                "symbol": r.get("symbol"),
                "exchange": r.get("exchange") or "NASDAQ",
                "name": r.get("name", ""),
                "market_cap": r.get("market_cap"),
            }
            for r in resolved
            if r.get("symbol")
        ]
        return rows, {
            "source": "snapshot",
            "force_keys": [],
            "scan_id": params.get("universe_scan_id"),
        }

    parsed = parse_force_include_text(params.get("force_symbols", ""))
    if not parsed.symbols:
        detail = "; ".join(parsed.errors) or "no valid symbols parsed"
        raise ValueError(f"Force include parse failed: {detail}")
    keys = [list(k) for k in parsed.symbols]
    rows = [{"symbol": k[0], "exchange": k[1]} for k in keys]
    return rows, {"source": "paste", "force_keys": keys, "scan_id": None}


def _graph_node_emitter(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """SSE on_node callback for run_graph: thread-safe ``node`` events."""

    def emit(node_id: str, tool_id: str, status: str, kept: int, total: int) -> None:
        event = {
            "type": "node",
            "node_id": node_id,
            "tool_id": tool_id,
            "status": status,
            "kept": kept,
            "total": total,
        }
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            pass

    return emit


async def run_graph_job(
    run_id: str,
    params: dict[str, Any],
    repo: Repo,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
) -> None:
    """Execute a component graph definition and persist per-node artifacts."""
    graph = params.get("graph")
    if not isinstance(graph, dict):
        await repo.set_status(run_id, "failed", error="graph run requires a graph")
        await queue.put({"type": "failed", "error": "graph run requires a graph"})
        return

    try:
        universe_rows, universe = await asyncio.to_thread(resolve_universe, params)
        definition = to_walker_definition(graph, universe=universe)
        errors = validate_graph(definition)
        if errors:
            raise ValueError("graph invalid: " + "; ".join(errors))

        result = await asyncio.to_thread(
            run_graph,
            definition,
            universe_rows,
            node_overrides=params.get("node_overrides") or {},
            on_node=_graph_node_emitter(queue, loop),
        )
    except Exception as exc:
        logger.error("Graph run %s failed: %s", run_id, exc)
        await repo.set_status(run_id, "failed", error=str(exc))
        await queue.put({"type": "failed", "error": str(exc)})
        return

    try:
        counts: dict[str, Any] = {"reports": result.merge_table["count"], "degraded": result.degraded}
        for node_id, node_result in result.nodes.items():
            await repo.upsert_artifact(
                run_id,
                f"node:{node_id}",
                {
                    "tool_id": node_result.tool_id,
                    "output_rows": node_result.output_rows,
                    "errors": node_result.errors,
                    "dropped": node_result.dropped,
                    "duration_ms": node_result.duration_ms,
                    "error": node_result.error,
                },
            )
        await repo.upsert_artifact(run_id, "merge_table", result.merge_table)
        await repo.upsert_artifact(
            run_id, "universe", {"rows": universe_rows, "config": universe}
        )
        await repo.set_status(run_id, "succeeded", counts=counts)
        await queue.put(
            {
                "type": "done",
                "counts": counts,
                "degraded": result.degraded,
                "merge_table": result.merge_table,
            }
        )
    except Exception as exc:
        logger.error("Persisting graph run %s failed: %s", run_id, exc)
        await repo.set_status(run_id, "failed", error=f"persist failed: {exc}")
        await queue.put({"type": "failed", "error": str(exc)})


def build_run_config(params: dict[str, Any]) -> RunConfig:
    """Map an API request body to a pipeline ``RunConfig``.

    Paste parsing is shared with the CLI via ``parse_force_include_text``; the
    parsed ``SymbolKey`` tuples become ``force_keys``. A market-wide sweep
    (``use_screener=True``) skips paste parsing and leaves ``force_keys`` empty.
    """
    pipeline_type = params["pipeline_type"]
    use_screener = bool(params.get("use_screener", False))

    if use_screener:
        force_keys: list[Any] = []
    else:
        parsed = parse_force_include_text(params.get("force_symbols", ""))
        if not parsed.symbols:
            detail = "; ".join(parsed.errors) or "no valid symbols parsed"
            raise ValueError(f"Force include parse failed: {detail}")
        force_keys = parsed.symbols

    config: dict[str, Any] = dict(
        name=params.get("name") or "scan",
        pipeline_type=pipeline_type,
        force_keys=force_keys,
        use_screener=use_screener,
        output_root=params.get("output_root") or "output",
    )

    if pipeline_type == "daily_ep_scan":
        config["select"] = params.get("select", "strict")
        config["run_catalyst"] = params.get("run_catalyst", True)
        config["apply_gates"] = params.get("apply_gates", True)
    elif pipeline_type == "daily_vcp_scan":
        config["apply_gates"] = params.get("apply_gates", True)
    elif pipeline_type == "daily_bo_scan":
        config["apply_gates"] = params.get("apply_gates", True)
        config["bo_profile"] = params.get("bo_profile", "best")

    return RunConfig(**config)


def read_artifacts(run_dir: Path) -> dict[str, Any]:
    """Read ``run_meta.json`` + ``*_agent{1,2,3}.json`` back from a run directory."""
    artifacts: dict[str, Any] = {}
    meta_path = run_dir / "run_meta.json"
    if meta_path.is_file():
        artifacts["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
    for stage in _ARTIFACT_STAGES:
        matches = sorted(run_dir.glob(f"*_{stage}.json"))
        if matches:
            artifacts[stage] = json.loads(matches[0].read_text(encoding="utf-8"))
    return artifacts


def extract_counts(artifacts: dict[str, Any], pipeline_type: str) -> dict[str, Any]:
    agent1 = artifacts.get("agent1") or {}
    if pipeline_type == "daily_ep_scan":
        return {
            "baseline": (agent1.get("baseline") or {}).get("count", 0),
            "strict": (agent1.get("strict") or {}).get("count", 0),
        }
    return agent1.get("counts") or {}


async def run_scan_job(
    run_id: str,
    params: dict[str, Any],
    repo: Repo,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
) -> None:
    """Run a scan to completion and persist the result.

    ``run_daily`` is synchronous and long-running (5–10 min), so it runs in a
    worker thread while this coroutine stays on the event loop.
    """
    reporter = EventReporter(queue, loop)

    if params.get("graph") is not None:
        await run_graph_job(run_id, params, repo, loop, queue)
        return

    try:
        config = build_run_config(params)
    except Exception as exc:
        logger.error("Run config failed: %s", exc)
        await repo.set_status(run_id, "failed", error=str(exc))
        await queue.put({"type": "failed", "error": str(exc)})
        return

    try:
        result = await asyncio.to_thread(lambda: run_daily(config, reporter=reporter))
    except Exception as exc:
        logger.error("Run %s failed: %s", run_id, exc)
        await repo.set_status(run_id, "failed", error=str(exc))
        await queue.put({"type": "failed", "error": str(exc)})
        return

    try:
        artifacts = read_artifacts(result.run_dir)
        counts = extract_counts(artifacts, config.pipeline_type)
        for stage, payload in artifacts.items():
            await repo.upsert_artifact(run_id, stage, payload)
        if result.error:
            await repo.set_status(run_id, "failed", error=result.error, counts=counts)
            await queue.put({"type": "failed", "error": result.error})
        else:
            await repo.set_status(run_id, "succeeded", counts=counts)
            await queue.put(
                {
                    "type": "done",
                    "exit_code": result.exit_code,
                    "counts": counts,
                    "steps_completed": result.steps_completed,
                }
            )
    except Exception as exc:
        logger.error("Persisting run %s failed: %s", run_id, exc)
        await repo.set_status(run_id, "failed", error=f"persist failed: {exc}")
        await queue.put({"type": "failed", "error": str(exc)})


class JobManager:
    """Registry of in-flight runs: one event queue and one task per run id."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def start(
        self,
        run_id: str,
        params: dict[str, Any],
        repo: Repo,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[run_id] = queue
        task = asyncio.create_task(run_scan_job(run_id, params, repo, loop, queue))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _t: self.tasks.pop(run_id, None))

    def queue_for(self, run_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(run_id)
