"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { MergeTable } from "@/components/MergeTable";
import { ProgressPanel, type ProgressState } from "@/components/ProgressPanel";
import { ResultsTable } from "@/components/ResultsTable";
import { getRun, PIPELINE_LABELS, subscribeToRunEvents } from "@/lib/api";
import type { MergeTable as MergeTableData, RunDetail, RunEvent } from "@/lib/types";

function reduceProgress(prev: ProgressState, e: RunEvent): ProgressState {
  const events = [...prev.events, e];
  if (e.type === "ticker_begin") {
    return { ...prev, events, ticker: { total: e.total ?? 0, description: e.description ?? "", index: 0, symbol: "" } };
  }
  if (e.type === "ticker") {
    return {
      ...prev,
      events,
      ticker: {
        total: e.total ?? prev.ticker?.total ?? 0,
        description: prev.ticker?.description ?? "",
        index: e.index ?? 0,
        symbol: e.symbol ?? "",
      },
    };
  }
  if (e.type === "done") {
    return { ...prev, events, done: true };
  }
  if (e.type === "failed") {
    return { ...prev, events, failed: true, error: e.error };
  }
  return { ...prev, events };
}

export default function RunDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [run, setRun] = useState<RunDetail | null>(null);
  const [progress, setProgress] = useState<ProgressState>({ events: [], done: false, failed: false });
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    getRun(id)
      .then((r) => {
        setRun(r);
        if (r.status === "succeeded" || r.status === "failed") {
          setProgress((p) => ({ ...p, done: r.status === "succeeded", failed: r.status === "failed", error: r.error ?? undefined }));
        }
      })
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    const unsub = subscribeToRunEvents(id, (e) => setProgress((p) => reduceProgress(p, e)));
    return unsub;
  }, [id]);

  useEffect(() => {
    if (progress.done || progress.failed) {
      getRun(id).then(setRun).catch(() => {});
    }
  }, [progress.done, progress.failed, id]);

  const pipelineLabel = run ? PIPELINE_LABELS[run.pipeline_type] ?? run.pipeline_type : "";

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-6">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← Dashboard
        </Link>
        <div className="mt-2 flex items-baseline justify-between">
          <h1 className="text-2xl font-bold">{run?.name ?? "Run"}</h1>
          {run && (
            <span className="text-sm text-slate-400">
              {pipelineLabel} · {run.status}
            </span>
          )}
        </div>
      </header>

      <div className="space-y-6">
        <ProgressPanel state={progress} />

        {run?.artifacts && (
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Results</h2>
              <button
                onClick={() => setShowRaw((v) => !v)}
                className="text-xs text-cyan-300 hover:underline"
              >
                {showRaw ? "Hide raw JSON" : "Show raw JSON"}
              </button>
            </div>

            {showRaw ? (
              <pre className="overflow-auto rounded-lg border border-slate-800 bg-slate-900 p-4 text-xs text-slate-300">
                {JSON.stringify(run.artifacts, null, 2)}
              </pre>
            ) : run.artifacts.merge_table ? (
              <MergeTable table={run.artifacts.merge_table as MergeTableData} />
            ) : (
              <ResultsTable artifacts={run.artifacts} pipelineType={run.pipeline_type} />
            )}
          </section>
        )}
      </div>
    </main>
  );
}
