# Full-stack Scan Dashboard

- **Purpose**: Wrap the `stock_analyze` scan pipeline in a single-user web dashboard — Next.js frontend (`web/`) + FastAPI service (`server/`) that runs scans as background jobs and persists runs to Neon Postgres.
- **Key entry points**: `server/app/main.py:26` → `create_app()`; `server/app/routes/runs.py:75` → `create_run`; `server/app/jobs.py:78` → `run_scan_job`; `web/lib/api.ts` → `createRun`/`listRuns`/`getRun`/`subscribeToRunEvents`.
- **Depends on**: `stock_analyze` package (editable-installed via root `pyproject.toml`), `asyncpg`, `fastapi`, `uvicorn`, `pydantic`.
- **Depended by**: nothing else in-repo; the frontend consumes `server` over HTTP/SSE.

## Architecture

```
web/ (Next.js App Router)
  app/page.tsx            dashboard — list runs
  app/new/page.tsx        new-scan form
  app/runs/[id]/page.tsx  live progress (SSE) + results
  lib/api.ts              REST + SSE client (BASE = NEXT_PUBLIC_API_URL)
        │  POST /api/runs, GET /api/runs, GET /api/runs/{id}, GET /api/runs/{id}/events
        ▼
server/ (FastAPI)
  app/routes/runs.py      REST + SSE endpoints
  app/jobs.py             build_run_config → run_daily (asyncio.to_thread) → read_artifacts → persist
  app/reporter.py         EventReporter (RunProgress duck-type) → asyncio.Queue
  app/db.py               Repo (asyncpg) over runs + run_artifacts (JSONB)
  app/schema.sql          CREATE TABLE IF NOT EXISTS (idempotent bootstrap)
        │
        ▼
stock_analyze/            unchanged pipeline (run_daily, RunConfig, RunResult)
        │
        ▼
Neon Postgres             runs + run_artifacts
```

## Key Symbols

| Symbol | File:Line | Role |
|--------|-----------|------|
| `create_app(repo=None)` | `server/app/main.py:26` | App factory; inject a fake `Repo` for tests; CORS `*`; mounts `runs_router` + `/api/health`. |
| `_lifespan` | `server/app/main.py:18` | On startup: `connect_repo()` + fresh `JobManager`; on shutdown: `close_repo()`. |
| `RunCreate` | `server/app/schemas.py:10` | Request body: `name`, `pipeline_type` (EP/VCP/BO), `force_symbols`, `select`, `run_catalyst`, `apply_gates`, `bo_profile`. Validators reject empty symbols and unknown pipeline. |
| `Repo` | `server/app/db.py:47` | asyncpg CRUD: `create_run`, `get_run`, `list_runs`, `set_status`, `upsert_artifact`, `get_artifacts`. JSONB encoded via `_dump`/`_load` (asyncpg returns `str`). |
| `connect_repo` | `server/app/db.py:129` | Creates pool, executes `schema.sql` (idempotent), returns `Repo`. |
| `EventReporter` | `server/app/reporter.py:24` | Duck-types `RunProgress`. `_emit` uses `loop.call_soon_threadsafe(queue.put_nowait, event)` because the pipeline calls from a worker thread. `console` is a `_ConsoleShim`. |
| `build_run_config` | `server/app/jobs.py:22` | Maps request body → `RunConfig`; shares `parse_force_include_text` with the CLI; sets per-pipeline params (EP `select`, BO `bo_profile`). |
| `read_artifacts` | `server/app/jobs.py:55` | Reads `run_meta.json` + `*_agent{1,2,3}.json` from `run_dir` via glob. |
| `extract_counts` | `server/app/jobs.py:68` | EP → `{baseline, strict}` from agent1; VCP/BO → agent1 `counts`. |
| `run_scan_job` | `server/app/jobs.py:78` | Build config → `asyncio.to_thread(run_daily)` → persist artifacts → `set_status(succeeded|failed)` → push terminal event. |
| `JobManager` | `server/app/jobs.py:132` | `start()` creates a queue + task per run; `queue_for()` for SSE. |
| `_event_stream` | `server/app/routes/runs.py:39` | SSE generator; replays terminal event from DB if already finished; 15s keep-alive heartbeat. |
| `create_run` | `server/app/routes/runs.py:75` | POST handler: generate `uuid4`, insert `queued` row, `manager.start()`. |
| `subscribeToRunEvents` | `web/lib/api.ts` | `EventSource` wrapper; parses `progress`/`done`/`failed` event data (payload `type` field is authoritative). |

## Edge Cases / Gotchas

- **Thread-safety**: the pipeline runs in a worker thread (`asyncio.to_thread`), so reporter events must cross the thread boundary via `call_soon_threadsafe` — never `queue.put_nowait` directly.
- **`find_dotenv` + moved tests**: `python-dotenv` resolves `.env` from the caller frame's `co_filename`; stale `__pycache__` (moved with `tests/`) carried old `tests/` paths and broke `load_dotenv()` with `OSError: Starting path not found`. Always clear `__pycache__` after relocating files.
- **SSE late subscriber**: if a run already finished, `_event_stream` replays a single terminal event from the DB (`_terminal_event`) instead of reading the (possibly drained) queue.
- **`run_meta.json` is NOT persisted as `meta` stage unless it exists** — `read_artifacts` only writes stages for files present (catalyst-off runs lack `agent2`).
- **`force_keys` empty → `ValueError`** both in `build_run_config` (paste parse) and `run_daily`; the job turns this into a `failed` run with the error persisted.
- **CORS `*`** for dev; tighten before any multi-user/credentialed deployment.
- **`output_root` default** is `output/` relative to the server's CWD — set `OUTPUT_ROOT` to an absolute path in production.

## Test coverage

- `server/tests/core/` — the migrated legacy suite (379 tests; 19 `screener`-marked deselected).
- `server/tests/` — new: `test_reporter`, `test_jobs`, `test_routes` (fake `Repo` + patched `run_daily`), `test_e2e_flow` (mocked `run_daily` exercising the reporter duck-type), `test_db` (real Postgres, gated on `TEST_DATABASE_URL`). Shared fake: `server/tests/fakes.py:FakeRepo`.
- `web/__tests__/` — Vitest: `api`, `ScanForm`, `ResultsTable`, `page` (dashboard). Config: `web/vitest.config.ts` (jsdom, `@` alias).
