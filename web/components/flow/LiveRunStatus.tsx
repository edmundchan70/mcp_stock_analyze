"use client";

import { useEffect, useState } from "react";
import { controlRun } from "@/lib/api";
import type { StampedRunEvent, RunTerminal } from "@/lib/runEvents";

export interface TickerState {
  description: string;
  total: number;
  index: number;
  symbol: string | null;
  done: boolean;
}

/**
 * Fold the SSE event stream into the current per-symbol ticker span.
 * `ticker_begin` opens a span, `ticker` updates the live symbol/count, and
 * `ticker_end` marks it done (the next `ticker_begin` resets it). Throttled
 * events mean `index` may jump — never assume +1 increments.
 */
export function deriveTicker(events: StampedRunEvent[]): TickerState | null {
  let state: TickerState | null = null;
  for (const { event } of events) {
    switch (event.type) {
      case "ticker_begin":
        state = {
          description: event.description ?? "Processing",
          total: event.total ?? 0,
          index: 0,
          symbol: null,
          done: false,
        };
        break;
      case "ticker":
        if (state) state = advanceTicker(state, event.index ?? state.index, event.symbol ?? null, false);
        break;
      case "ticker_end":
        if (state) state = advanceTicker(state, state.index, state.symbol, true);
        break;
      default:
        break;
    }
  }
  return state;
}

function advanceTicker(prev: TickerState, index: number, symbol: string | null, done: boolean): TickerState {
  return {
    description: prev.description,
    total: prev.total,
    index,
    symbol,
    done,
  };
}

/** The node currently executing (most recent `node` running event not yet closed). */
export function deriveRunningNode(events: StampedRunEvent[]): string | null {
  let running: string | null = null;
  for (const { event } of events) {
    if (event.type !== "node") continue;
    if (event.status === "running") running = event.node_id ?? null;
    else if (running !== null && running === event.node_id) running = null;
  }
  return running;
}

export function LiveRunStatus({
  runId,
  events,
  runTerminal,
}: {
  runId: string | null;
  events: StampedRunEvent[];
  runTerminal: RunTerminal;
}) {
  const [paused, setPaused] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const ev = events[events.length - 1]?.event;
    if (ev?.type === "control") {
      if (ev.action === "pause") setPaused(true);
      else if (ev.action === "resume") setPaused(false);
    }
  }, [events]);

  const ticker = deriveTicker(events);
  const runningNode = deriveRunningNode(events);
  const running = runTerminal === "running";
  const pct = ticker && ticker.total > 0 ? Math.min(100, Math.round((ticker.index / ticker.total) * 100)) : 0;

  async function act(action: string, nodeId?: string) {
    if (!runId) return;
    setBusy(true);
    try {
      await controlRun(runId, action, nodeId);
    } catch {
      // Control calls are best-effort; failures surface in the activity feed.
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-2xs font-semibold uppercase tracking-wider text-slate-500">Live status</h3>
        {running && <span className="h-2 w-2 animate-pulse rounded-full bg-accent-500" />}
      </div>

      {ticker ? (
        <div className="space-y-2">
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-slate-500">{ticker.description}</span>
            {ticker.done ? (
              <span className="text-sm font-semibold text-up-500">done</span>
            ) : ticker.symbol ? (
              <span className="font-mono text-lg font-semibold text-accent-400">{ticker.symbol}</span>
            ) : (
              <span className="text-sm text-slate-600">starting…</span>
            )}
            <span className="tnum ml-auto font-mono text-xs text-slate-500">
              {ticker.index}/{ticker.total}
            </span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded bg-ink-800">
            <div
              className={`h-full transition-all duration-300 ${ticker.done ? "bg-up-500" : "bg-accent-500"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-600">
          {running ? "Starting…" : runTerminal === "succeeded" ? "Run complete" : "Idle"}
        </p>
      )}

      {running && (
        <div className="mt-3 flex items-center gap-2">
          <button type="button" className="btn-ghost px-2.5 py-1 text-xs" disabled={busy} onClick={() => act(paused ? "resume" : "pause")}>
            {paused ? "Resume" : "Pause"}
          </button>
          {runningNode && (
            <button type="button" className="btn-ghost px-2.5 py-1 text-xs" disabled={busy} onClick={() => act("skip", runningNode)}>
              Skip node
            </button>
          )}
          <button type="button" className="btn-danger px-2.5 py-1 text-xs" disabled={busy} onClick={() => act("cancel")}>
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}
