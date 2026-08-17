"""FastAPI application factory for the scan dashboard server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_database_url
from .db import Repo, close_repo, connect_repo
from .jobs import JobManager
from .routes.definitions import router as definitions_router
from .routes.runs import router as runs_router
from .routes.tools import router as tools_router
from .seed import seed_default_definitions

from stock_analyze.tools import validate_registry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    registry_errors = validate_registry()
    if registry_errors:
        raise RuntimeError("tool registry failed startup validation:\n" + "\n".join(registry_errors))
    repo = await connect_repo(get_database_url())
    try:
        interrupted = await repo.mark_interrupted_runs()
        if interrupted:
            logger.info("marked %d interrupted run(s) as failed", interrupted)
    except Exception:
        logger.exception("marking interrupted runs failed")
    try:
        await seed_default_definitions(repo)
    except Exception:
        logger.exception("seeding default pipeline definitions failed")
    app.state.repo = repo
    app.state.job_manager = JobManager()
    yield
    await close_repo(repo)


def create_app(repo: Optional[Repo] = None) -> FastAPI:
    """Create the app. Pass ``repo`` to inject a fake/test repository."""
    app = FastAPI(title="stock-analyze server", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.repo = repo
    app.state.job_manager = JobManager()
    app.include_router(runs_router)
    app.include_router(tools_router)
    app.include_router(definitions_router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
