"use client";

import { useState } from "react";
import Link from "next/link";
import { controlRun, PIPELINE_LABELS } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const STATUS_TONE: Record<string, string> = {
  queued: "bg-slate-700 text-slate-200",
  running: "bg-blue-900 text-blue-200",
  succeeded: "bg-emerald-900 text-emerald-200",
  failed: "bg-rose-900 text-rose-200",
  cancelled: "bg-slate-800 text-slate-300",
};

function statusLabel(run: RunSummary): string {
  if (run.paused) return "paused";
  if (run.awaiting_confirmation) return "awaiting confirmation";
  return run.status;
}

export function RunTable({ runs, onChanged }: { runs: RunSummary[]; onChanged?: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(runId: string, action: string, nodeId?: string, decision?: string) {
    setBusy(runId);
    setError(null);
    try {
      await controlRun(runId, action, nodeId, decision);
      onChanged?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
        No scans yet. Start one to see results here.
      </div>
    );
  }

  return (
    <div>
      {error && <p className="mb-3 text-xs text-rose-400">{error}</p>}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Pipeline</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Results</th>
              <th className="px-4 py-3 font-medium">Started</th>
              <th className="px-4 py-3 font-medium">Controls</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {runs.map((run) => {
              const active = run.status === "running" || run.status === "queued";
              const confirm = run.awaiting_confirmation;
              return (
                <tr key={run.id} className="hover:bg-slate-900/40">
                  <td className="px-4 py-3">
                    <Link href={`/runs/${run.id}`} className="font-medium text-cyan-300 hover:underline">
                      {run.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {PIPELINE_LABELS[run.pipeline_type] ?? run.pipeline_type}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_TONE[run.status] ?? "bg-slate-700 text-slate-200"}`}>
                      {statusLabel(run)}
                    </span>
                    {confirm && (
                      <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
                        {confirm.symbol_count} symbols
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {run.counts
                      ? Object.entries(run.counts)
                          .map(([k, v]) => `${k}=${v}`)
                          .join(" ")
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {confirm ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => act(run.id, "confirm", confirm.node_id, "proceed")}
                          disabled={busy === run.id}
                          className="rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                        >
                          Proceed
                        </button>
                        <button
                          onClick={() => act(run.id, "confirm", confirm.node_id, "skip")}
                          disabled={busy === run.id}
                          className="rounded bg-slate-800 px-2 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
                        >
                          Skip
                        </button>
                        <button
                          onClick={() => act(run.id, "confirm", confirm.node_id, "cancel")}
                          disabled={busy === run.id}
                          className="rounded bg-rose-600 px-2 py-1 text-xs font-medium text-white hover:bg-rose-500 disabled:opacity-40"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : active ? (
                      <button
                        onClick={() => act(run.id, "cancel")}
                        disabled={busy === run.id}
                        className="rounded bg-rose-600 px-2 py-1 text-xs font-medium text-white hover:bg-rose-500 disabled:opacity-40"
                      >
                        Cancel
                      </button>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
