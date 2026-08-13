"""FastAPI application factory for the scan dashboard server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_database_url
from .db import Repo, close_repo, connect_repo
from .jobs import JobManager
from .routes.runs import router as runs_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    repo = await connect_repo(get_database_url())
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

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
