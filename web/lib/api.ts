import type { RunDetail, RunEvent, RunSummary } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export async function listRuns(): Promise<RunSummary[]> {
  const res = await fetch(`${BASE}/api/runs`);
  const data = await handle<{ runs: RunSummary[] }>(res);
  return data.runs;
}

export async function getRun(id: string): Promise<RunDetail> {
  const res = await fetch(`${BASE}/api/runs/${id}`);
  return handle<RunDetail>(res);
}

export async function createRun(body: Record<string, unknown>): Promise<RunSummary> {
  const res = await fetch(`${BASE}/api/runs`, {
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
    if (event.type === "done" || event.type === "failed") {
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
};
