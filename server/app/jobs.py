"""Background scan jobs: build RunConfig, run run_daily in a thread, persist artifacts."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from stock_analyze.force_include import parse_force_include_text
from stock_analyze.pipeline import RunConfig, run_daily

from .db import Repo
from .reporter import EventReporter

logger = logging.getLogger(__name__)

_ARTIFACT_STAGES = ("agent1", "agent2", "agent3")


def build_run_config(params: dict[str, Any]) -> RunConfig:
    """Map an API request body to a pipeline ``RunConfig``.

    Paste parsing is shared with the CLI via ``parse_force_include_text``; the
    parsed ``SymbolKey`` tuples become ``force_keys``.
    """
    pipeline_type = params["pipeline_type"]
    parsed = parse_force_include_text(params.get("force_symbols", ""))
    if not parsed.symbols:
        detail = "; ".join(parsed.errors) or "no valid symbols parsed"
        raise ValueError(f"Force include parse failed: {detail}")

    config: dict[str, Any] = dict(
        name=params.get("name") or "scan",
        pipeline_type=pipeline_type,
        force_keys=parsed.symbols,
        use_screener=False,
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
