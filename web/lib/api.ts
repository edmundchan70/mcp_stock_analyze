import type {
  ComponentTemplate,
  GraphDefinition,
  OhlcvResponse,
  PipelineDefinition,
  PreviewResponse,
  RunDetail,
  RunEvent,
  RunSummary,
  ToolSpec,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Fail fast instead of hanging forever when the backend is down or wedged
// (e.g. uvicorn --reload deadlock on Windows). The home page polls runs every
// 5s, so keep this below the poll interval to avoid overlapping requests.
const REQUEST_TIMEOUT_MS = 4000;

const UNREACHABLE =
  `Backend unreachable (${BASE}). Is the API server running? ` +
  `Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s.`;

/**
 * fetch with an abort timeout. Turns a wedged/absent backend into a clear
 * error instead of leaving the UI on an eternal "Loading…".
 */
async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${BASE}${path}`, { ...init, signal: controller.signal });
  } catch (e) {
    if (controller.signal.aborted) throw new Error(UNREACHABLE);
    throw new Error(
      `Backend unreachable (${BASE}) — ${e instanceof Error ? e.message : String(e)}`,
    );
  } finally {
    clearTimeout(timer);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export async function listRuns(): Promise<RunSummary[]> {
  const res = await apiFetch("/api/runs");
  const data = await handle<{ runs: RunSummary[] }>(res);
  return data.runs;
}

export async function getRun(id: string): Promise<RunDetail> {
  const res = await apiFetch(`/api/runs/${id}`);
  return handle<RunDetail>(res);
}

export async function createRun(body: Record<string, unknown>): Promise<RunSummary> {
  const res = await apiFetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<RunSummary>(res);
}

/**
 * Subscribe to a run's progress stream. Returns an unsubscribe function.
 * The EventSource auto-reconnects; the server replays a terminal event once
 * the run is finished so late subscribers still resolve.
 */
export function subscribeToRunEvents(id: string, onEvent: (e: RunEvent) => void): () => void {
  const es = new EventSource(`${BASE}/api/runs/${id}/events`);
  const parse = (ev: Event): RunEvent => JSON.parse((ev as MessageEvent).data as string) as RunEvent;
  const handle = (ev: Event) => {
    const event = parse(ev);
    onEvent(event);
    // The server closes the stream after a terminal event; prevent EventSource
    // from auto-reconnecting (which would replay "done" forever).
    if (event.type === "done" || event.type === "failed" || event.type === "cancelled") {
      es.close();
    }
  };
  es.addEventListener("progress", handle);
  es.addEventListener("done", handle);
  es.addEventListener("failed", handle);
  return () => es.close();
}

export const PIPELINE_LABELS: Record<string, string> = {
  daily_ep_scan: "Episodic Pivot (EP)",
  daily_vcp_scan: "VCP",
  daily_bo_scan: "Qullamaggie BO",
  daily_zhao_scan: "照妖鏡",
  daily_premarket_scan: "Premarket grep",
};

// ── component graph editor API (T13/T20/T22) ───────────────────────

export async function listTools(): Promise<ToolSpec[]> {
  const res = await apiFetch("/api/tools");
  const data = await handle<{ tools: ToolSpec[] }>(res);
  return data.tools;
}

export async function listDefinitions(): Promise<PipelineDefinition[]> {
  const res = await apiFetch("/api/definitions");
  const data = await handle<{ definitions: PipelineDefinition[] }>(res);
  return data.definitions;
}

export async function saveDefinition(body: { name: string; graph: GraphDefinition }, id?: string): Promise<PipelineDefinition> {
  const res = await apiFetch(`/api/definitions/${id ?? ""}`, {
    method: id ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<PipelineDefinition>(res);
}

export async function deleteDefinition(id: string): Promise<void> {
  await apiFetch(`/api/definitions/${id}`, { method: "DELETE" });
}

export async function listComponentTemplates(): Promise<ComponentTemplate[]> {
  const res = await apiFetch("/api/component-templates");
  const data = await handle<{ templates: ComponentTemplate[] }>(res);
  return data.templates;
}

export async function saveComponentTemplate(body: Omit<ComponentTemplate, "id">): Promise<ComponentTemplate> {
  const res = await apiFetch("/api/component-templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<ComponentTemplate>(res);
}

export async function deleteComponentTemplate(id: string): Promise<void> {
  await apiFetch(`/api/component-templates/${id}`, { method: "DELETE" });
}

export async function previewRun(body: Record<string, unknown>): Promise<PreviewResponse> {
  const res = await apiFetch("/api/runs/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<PreviewResponse>(res);
}

/**
 * Fetch daily OHLCV bars for a batch of symbols (pattern-phase chart evidence).
 */
export async function fetchOhlcv(
  symbols: { symbol: string; exchange?: string }[],
  bars = 300,
): Promise<Record<string, OhlcvResponse["symbols"][string]>> {
  const res = await apiFetch("/api/ohlcv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbols: symbols.map((s) => ({ symbol: s.symbol, exchange: s.exchange ?? "NASDAQ" })),
      bars,
    }),
  });
  const data = await handle<OhlcvResponse>(res);
  return data.symbols;
}

/**
 * Apply a runtime control action to an in-flight graph run
 * (skip / pause / resume / cancel / confirm).
 */
export async function controlRun(
  id: string,
  action: string,
  nodeId?: string,
  decision?: string,
): Promise<void> {
  const res = await apiFetch(`/api/runs/${id}/control`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, node_id: nodeId, decision }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text.slice(0, 200)}`);
  }
}
