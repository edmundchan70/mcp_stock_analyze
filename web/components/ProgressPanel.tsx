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
    <div className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-2xs font-semibold uppercase tracking-wider text-slate-500">Progress</h2>
        {!state.done && !state.failed && (
          <span className="animate-pulse text-xs text-accent-400">running…</span>
        )}
      </div>

      {state.ticker && (
        <div className="mb-3 rounded-md border border-ink-800 bg-ink-850 px-3 py-2 font-mono text-xs text-slate-400">
          {state.ticker.description}: {state.ticker.index}/{state.ticker.total}{" "}
          <span className="text-accent-400">{state.ticker.symbol}</span>
        </div>
      )}

      <ul className="space-y-1 font-mono text-xs">
        {stageEvents.length === 0 && !state.done && !state.failed && (
          <li className="text-slate-600">Waiting for the scan to start…</li>
        )}
        {stageEvents.map((e, i) => (
          <li
            key={i}
            className={
              e.type === "fail"
                ? "text-down-500"
                : e.type === "stage_done"
                  ? "text-up-500"
                  : e.type === "console"
                    ? "text-slate-600"
                    : "text-slate-400"
            }
          >
            {e.text}
          </li>
        ))}
        {state.failed && <li className="text-down-500">{state.error ?? "Scan failed"}</li>}
        {state.done && <li className="text-up-500">Scan complete</li>}
      </ul>
    </div>
  );
}
