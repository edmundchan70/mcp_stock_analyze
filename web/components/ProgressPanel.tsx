"use client";

import type { RunEvent } from "@/lib/types";

export interface ProgressState {
  events: RunEvent[];
  ticker?: { total: number; description: string; index: number; symbol: string };
  done: boolean;
  failed: boolean;
  error?: string;
}

export function ProgressPanel({ state }: { state: ProgressState }) {
  const stageEvents = state.events.filter((e) =>
    ["stage", "stage_done", "fail", "console"].includes(e.type),
  );

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Progress</h2>
        {!state.done && !state.failed && (
          <span className="animate-pulse text-xs text-blue-300">running…</span>
        )}
      </div>

      {state.ticker && (
        <div className="mb-3 rounded-md bg-slate-900 px-3 py-2 text-sm text-slate-300">
          {state.ticker.description}: {state.ticker.index}/{state.ticker.total} {state.ticker.symbol}
        </div>
      )}

      <ul className="space-y-1 font-mono text-xs">
        {stageEvents.length === 0 && !state.done && !state.failed && (
          <li className="text-slate-500">Waiting for the scan to start…</li>
        )}
        {stageEvents.map((e, i) => (
          <li
            key={i}
            className={
              e.type === "fail"
                ? "text-rose-400"
                : e.type === "stage_done"
                  ? "text-emerald-300"
                  : e.type === "console"
                    ? "text-slate-500"
                    : "text-slate-300"
            }
          >
            {e.text}
          </li>
        ))}
        {state.failed && <li className="text-rose-400">{state.error ?? "Scan failed"}</li>}
        {state.done && <li className="text-emerald-300">Scan complete</li>}
      </ul>
    </div>
  );
}
