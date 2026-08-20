"use client";

import { useState } from "react";
import Link from "next/link";
import { controlRun, PIPELINE_LABELS } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const STATUS_TONE: Record<string, string> = {
  queued: "bg-ink-700 text-slate-300",
  running: "bg-accent-600/15 text-accent-400",
  succeeded: "bg-up-600/15 text-up-500",
  failed: "bg-down-600/15 text-down-500",
  cancelled: "bg-ink-800 text-slate-500",
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
      <div className="panel p-8 text-center">
        <p className="text-sm text-slate-500">No scans yet.</p>
        <Link href="/flow" className="btn-primary mt-4">
          Start a guided scan
        </Link>
      </div>
    );
  }

  return (
    <div>
      {error && <p className="mb-3 text-xs text-down-500">{error}</p>}
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink-900 text-2xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Pipeline</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Results</th>
                <th className="px-4 py-3 font-medium">Started</th>
                <th className="px-4 py-3 font-medium">Controls</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800/60">
              {runs.map((run) => {
                const active = run.status === "running" || run.status === "queued";
                const confirm = run.awaiting_confirmation;
                return (
                  <tr key={run.id} className="hover:bg-ink-850/60">
                    <td className="px-4 py-3">
                      <Link href={`/runs/${run.id}`} className="font-medium text-accent-400 hover:underline">
                        {run.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {PIPELINE_LABELS[run.pipeline_type] ?? run.pipeline_type}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2.5 py-0.5 text-xs font-medium ${STATUS_TONE[run.status] ?? "bg-ink-700 text-slate-300"}`}>
                        {statusLabel(run)}
                      </span>
                      {confirm && (
                        <span className="ml-2 rounded bg-accent-600/15 px-1.5 py-0.5 text-2xs text-accent-400">
                          {confirm.symbol_count} symbols
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {run.counts
                        ? Object.entries(run.counts)
                            .map(([k, v]) => `${k}=${v}`)
                            .join(" ")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {confirm ? (
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => act(run.id, "confirm", confirm.node_id, "proceed")}
                            disabled={busy === run.id}
                            className="rounded bg-up-600 px-2 py-1 text-xs font-medium text-white hover:bg-up-500 disabled:opacity-40"
                          >
                            Proceed
                          </button>
                          <button
                            onClick={() => act(run.id, "confirm", confirm.node_id, "skip")}
                            disabled={busy === run.id}
                            className="rounded border border-ink-700 px-2 py-1 text-xs font-medium text-slate-300 hover:bg-ink-700 disabled:opacity-40"
                          >
                            Skip
                          </button>
                          <button
                            onClick={() => act(run.id, "confirm", confirm.node_id, "cancel")}
                            disabled={busy === run.id}
                            className="rounded bg-down-600 px-2 py-1 text-xs font-medium text-white hover:bg-down-500 disabled:opacity-40"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : active ? (
                        <button
                          onClick={() => act(run.id, "cancel")}
                          disabled={busy === run.id}
                          className="rounded bg-down-600 px-2 py-1 text-xs font-medium text-white hover:bg-down-500 disabled:opacity-40"
                        >
                          Cancel
                        </button>
                      ) : (
                        <span className="text-slate-700">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
