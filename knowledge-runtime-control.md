# Runtime Control for Component Graph Runs

- **Purpose**: Add interactive runtime controls (skip / pause / resume / cancel) and an AI-Search confirmation gate to in-flight component graph runs, plus honest persistence so runs survive navigation and server restarts.
- **Key entry points**: `server/app/routes/runs.py:199` → `control_run` endpoint; `stock_analyze/tools/walker.py:227` → `run_graph(..., control=, on_confirm=)`; `server/app/control.py:21` → `RunControl`; `web/components/GraphEditor.tsx` → editor controls + node status colors.
- **Depends on**: component graph walker (`stock_analyze/tools/`), search agents (`stock_analyze/agents/`), `server/app/jobs.py` JobManager, `web/lib/api.ts`.
- **Depended by**: dashboard / run-detail / editor frontends over HTTP + SSE.

## Architecture

```
UI (Dashboard / RunDetail / GraphEditor)
  │  controlRun(action, node_id?, decision?)  ── POST /api/runs/{id}/control
  ▼
control_run (routes/runs.py:199)
  │  dispatches on RunControl flags (threading.Event/Lock)
  ▼
RunControl (server/app/control.py:21)   ◄── owned by JobManager._controls
  │  checkpoint() observes pause/cancel; confirm state blocks the gate
  ▼
run_graph worker thread (walker.py:227, via asyncio.to_thread)
  │  per-node: skip pass-through → pause checkpoint → AI-Search confirm gate
  ▼
search callable (builtins.py:191) → agents (enrichment/catalyst/rating)
  │  per-symbol checkpoint kwarg (drain-then-freeze inside the semaphore)
  ▼
SSE (queue) ── node / confirm_needed / control / done / cancelled / failed
```

**Thread model**: the walker + search agents run in a worker thread (`asyncio.to_thread`), while the HTTP control endpoint runs on the event loop. All control state is guarded by `threading.Lock` / `threading.Event`. SSE events cross back via `loop.call_soon_threadsafe(queue.put_nowait, …)`.

**Control token plumbing**: `run_graph` registers the `RunControl` in a module-level registry and injects a JSON-safe `__control_id__` token into each node's `params` (`walker.py:270`). `_search_callable` recovers the control with `checkpoint_for(params.get("__control_id__"))` (`builtins.py:197`) so the agent `checkpoint` kwarg is populated without touching persisted `params`/`node_overrides` JSON. The token is unregistered in `run_graph`'s `finally` block.

## Key Symbols

| Symbol | File:Line | Role |
|--------|-----------|------|
| `RunCancelled` | `stock_analyze/tools/control.py:20` | Cooperative cancel exception raised at the next checkpoint once cancel is armed. |
| `register_control` / `get_control` / `unregister_control` | `stock_analyze/tools/control.py:29,37,45` | Thread-safe module-level `id → control` registry. |
| `checkpoint_for` | `stock_analyze/tools/control.py:53` | Builds the per-symbol `checkpoint` callable from a token (None when unset). |
| `RunControl` | `server/app/control.py:21` | One mutable control object per in-flight run: skip set, pause/cancel events, confirm events/state. |
| `RunControl.checkpoint` | `server/app/control.py:75` | Blocking callable: return immediately while running, drain-then-freeze while paused, raise `RunCancelled` once cancelled. |
| `RunControl.request_confirmation` / `wait_confirmation` / `confirm` / `pending_confirmation` | `server/app/control.py:89,102,111,121` | Confirmation-gate state: block a node until a `proceed|skip|cancel` decision arrives; `pending_confirmation` feeds the dashboard/run-detail "awaiting confirmation" state. |
| `run_graph` | `stock_analyze/tools/walker.py:227` | Walker signature gained `control=None` + `on_confirm=None`; skip pass-through, pause checkpoint, confirm gate, `RunCancelled` mapping. |
| confirm gate | `stock_analyze/tools/walker.py:311` | When `spec.id == "search"`, `confirm_threshold > 0`, and input rows > threshold (and not armed-skip), block on `request_confirmation`/`wait_confirmation`. |
| `_search_callable` | `stock_analyze/tools/builtins.py:191` | Reads `__control_id__` → `checkpoint_for` → passes `checkpoint=` to all three agents. |
| `enrich_with_vcp_context` | `stock_analyze/agents/enrichment.py:259,302` | `checkpoint` kwarg; called as first statement inside `async with sem` via `await asyncio.to_thread(checkpoint)` (drain-then-freeze). |
| `enrich_with_catalysts` | `stock_analyze/agents/catalyst.py:88,109` | `checkpoint` kwarg; called at top of the serial symbol loop. |
| `rate_ep_catalysts` | `stock_analyze/agents/rating.py:82,101` | `checkpoint` kwarg; called at top of the serial symbol loop. |
| `confirm_threshold` var | `stock_analyze/tools/variables.py:119` | AI-Search `SEARCH_VARS` entry: "Confirm above N symbols", default 50, 0 = never ask. |
| `_graph_node_emitter` | `server/app/jobs.py:67` | `on_node` SSE emitter (thread-safe `node` events with `status`). |
| `_graph_confirm_emitter` | `server/app/jobs.py:87` | `on_confirm` SSE emitter (`confirm_needed` events with `symbol_count`/`tavily_estimate`). |
| `run_graph_job` | `server/app/jobs.py:105` | Passes `control` + emitters to `run_graph`; maps `result.cancelled` → `cancelled` status + persists partial artifacts. |
| `JobManager._controls` / `control_for` | `server/app/jobs.py:316,340` | Per-run `RunControl` registry; `_cleanup` (done callback) pops it when the task ends. |
| `Repo.set_status` | `server/app/db.py:126` | Accepts `cancelled` as terminal (sets `finished_at`). |
| `Repo.mark_interrupted_runs` | `server/app/db.py:137` | Startup reconciliation: `queued`/`running` → `failed` with error `server restarted — run interrupted`. |
| `_attach_control_state` | `server/app/routes/runs.py:34` | Enriches `list_runs`/`get_run` payloads with `paused`, `skipped_nodes`, `awaiting_confirmation`. |
| `control_run` | `server/app/routes/runs.py:199` | `POST /api/runs/{id}/control`; dispatches `skip|pause|resume|cancel|confirm`, pushes an SSE `control` event, rejects finished/unknown/non-graph runs. |
| `_terminal_event` | `server/app/routes/runs.py:62` | Replays `cancelled` terminal event (with `merge_table` if persisted). |
| `ControlRequest` | `server/app/schemas.py:91` | Pydantic body validating `action ∈ CONTROL_ACTIONS`, `decision ∈ CONFIRM_DECISIONS`, `node_id`. |
| `controlRun` | `web/lib/api.ts` | Frontend client for the control endpoint. |
| `RunStatus` + `ConfirmationState` | `web/lib/types.ts` | `cancelled` added to status union; `ConfirmationState` + `paused`/`skipped_nodes`/`awaiting_confirmation` on `RunSummary`. |
| `ConfirmationModal` | `web/components/ConfirmationModal.tsx` | Proceed / Skip / Cancel modal (symbol count + ~2× Tavily estimate). |
| `RunTable` | `web/components/RunTable.tsx` | Status tones (incl. `cancelled`/`paused`/`awaiting confirmation`), per-row Cancel + inline Proceed/Skip/Cancel when awaiting. |
| dashboard poll | `web/app/page.tsx` | Auto-refresh every 5s while any run is in flight; stops once all runs are settled. |
| run detail | `web/app/runs/[id]/page.tsx` | Renders `node` progress (live via SSE, or reconstructed from `node:<id>` artifacts), cancel/pause buttons, confirmation modal. |
| GraphEditor controls | `web/components/GraphEditor.tsx` | Per-node skip buttons, pause/resume/cancel, node status ring colors, `confirm_needed` modal. |

## Control Semantics

- **skip** (pre-emptive): armed before the walker reaches the node; the node's input rows pass through unchanged and its `NodeResult.status` is `skipped`. Skip after a node has started is a no-op.
- **pause / resume**: pause freezes the walker at the next checkpoint (between nodes, or at the next per-symbol boundary inside search agents — in-flight ≤5 symbols drain); resume clears the flag.
- **cancel**: cooperative — the next checkpoint raises `RunCancelled`; the job maps it to `cancelled` status and persists whatever artifacts completed. Cancel also resolves a pending confirmation gate.
- **confirmation gate**: blocks the `search` node before any Tavily calls when input rows exceed `confirm_threshold`; the worker waits indefinitely on `wait_confirmation`. Decisions: `proceed` (run normally), `skip` (pass-through), `cancel` (raise `RunCancelled`). An armed skip suppresses the gate (skip-wins).

## Node statuses

`NodeResult.status` ∈ `ok | error | skipped | cancelled` (`stock_analyze/tools/walker.py`); surfaced via SSE `node` events, persisted in the `node:<node_id>` artifact, and replayed/rendered in the editor + run detail.

## Edge Cases / Gotchas

- **Cancel must be checked inside the walker node loop** (not only in agents): walker's per-node `except Exception` treats a callable failure as a degraded node, so `RunCancelled` is caught and re-raised explicitly to stop the run.
- **`confirm_threshold` is read from node `params`** — it must be present in `_tool_params` for the `search` node; default 50 lives in `SEARCH_VARS`.
- **Late SSE subscribers** get only a terminal event replay (`done`/`cancelled`/`failed`) — per-node progress is reconstructed client-side from `node:<id>` artifacts, not replayed.
- **The `__control_id__` token is per-run** and unregistered in `run_graph`'s `finally`, so control state cannot leak between runs or after completion.
- **Cancel while a confirmation gate is pending** must set the gate's decision to `cancel` and `.set()` the event, otherwise the blocked worker thread never wakes.
- **Legacy `run_daily` runs are out of scope** — `control_for` returns None for them and `control_run` rejects with 409 "not a controllable graph run".

## Test coverage

- `server/tests/test_control.py` — `RunControl` unit tests + control-endpoint integration (validation, 409s, cancel flag).
- `server/tests/core/test_walker_control.py` — skip pass-through, cancel between nodes, confirm gate proceed/skip/cancel/skip-wins.
- `server/tests/core/test_search_checkpoint.py` — checkpoint plumbing + `RunCancelled` propagation through the three agents.
- `web/__tests__/api.test.ts` — `controlRun` client; `web/__tests__/RunTable.test.tsx` — cancelled/awaiting-confirmation/cancel UI.
