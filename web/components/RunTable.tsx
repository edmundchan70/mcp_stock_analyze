"use client";

import Link from "next/link";
import { PIPELINE_LABELS } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const STATUS_TONE: Record<string, string> = {
  queued: "bg-slate-700 text-slate-200",
  running: "bg-blue-900 text-blue-200",
  succeeded: "bg-emerald-900 text-emerald-200",
  failed: "bg-rose-900 text-rose-200",
};

export function RunTable({ runs }: { runs: RunSummary[] }) {
  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
        No scans yet. Start one to see results here.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-400">
          <tr>
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Pipeline</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Results</th>
            <th className="px-4 py-3 font-medium">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {runs.map((run) => (
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
                  {run.status}
                </span>
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
