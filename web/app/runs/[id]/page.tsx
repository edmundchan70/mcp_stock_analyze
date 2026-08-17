"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ConfirmationModal } from "@/components/ConfirmationModal";
import { MergeTable } from "@/components/MergeTable";
import { ProgressPanel } from "@/components/ProgressPanel";
import { ResultsTable } from "@/components/ResultsTable";
import { controlRun, getRun, PIPELINE_LABELS, subscribeToRunEvents } from "@/lib/api";
import type {
  ConfirmationState,
  MergeTable as MergeTableData,
  RunDetail,
  RunEvent,
} from "@/lib/types";

interface NodeState {
  status: string;
  kept?: number;
}

interface RunProgressState {
  events: RunEvent[];
  ticker?: { total: number; description: string; index: number; symbol: string };
  done: boolean;
  failed: boolean;
  cancelled: boolean;
  error?: string;
  nodes: Record<string, NodeState>;
  confirmation: ConfirmationState | null;
}

const INITIAL: RunProgressState = {
  events: [],
  done: false,
  failed: false,
  cancelled: false,
  nodes: {},
  confirmation: null,
};

const NODE_TONE: Record<string, string> = {
  running: "text-blue-300",
  ok: "text-emerald-400",
  error: "text-rose-400",
  skipped: "text-slate-500",
  cancelled: "text-rose-400",
};

function reduceProgress(prev: RunProgressState, e: RunEvent): RunProgressState {
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
  if (e.type === "node" && e.node_id) {
    return {
      ...prev,
      events,
      nodes: { ...prev.nodes, [e.node_id]: { status: e.status ?? "running", kept: e.kept } },
    };
  }
  if (e.type === "confirm_needed" && e.node_id) {
    return {
      ...prev,
      events,
      confirmation: {
        node_id: e.node_id,
        symbol_count: e.symbol_count ?? null,
        tavily_estimate: e.tavily_estimate ?? null,
      },
    };
  }
  if (e.type === "control" && e.action === "resume") {
    return { ...prev, events };
  }
  if (e.type === "done") {
    return { ...prev, events, done: true };
  }
  if (e.type === "failed") {
    return { ...prev, events, failed: true, error: e.error };
  }
  if (e.type === "cancelled") {
    return { ...prev, events, cancelled: true };
  }
  return { ...prev, events };
}

function nodeStatusFromArtifacts(artifacts: Record<string, unknown>): Record<string, NodeState> {
  const out: Record<string, NodeState> = {};
  for (const [k, v] of Object.entries(artifacts)) {
    if (k.startsWith("node:") && v && typeof v === "object") {
      const node = v as { status?: string };
      out[k.slice(5)] = { status: node.status ?? "ok" };
    }
  }
  return out;
}

export default function RunDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [run, setRun] = useState<RunDetail | null>(null);
  const [progress, setProgress] = useState<RunProgressState>(INITIAL);
  const [showRaw, setShowRaw] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);

  useEffect(() => {
    getRun(id)
      .then((r) => {
        setRun(r);
        if (r.status === "succeeded" || r.status === "failed" || r.status === "cancelled") {
          setProgress((p) => ({
            ...p,
            done: r.status === "succeeded",
            failed: r.status === "failed",
            cancelled: r.status === "cancelled",
            error: r.error ?? undefined,
            nodes: nodeStatusFromArtifacts(r.artifacts),
          }));
        }
      })
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    const unsub = subscribeToRunEvents(id, (e) => setProgress((p) => reduceProgress(p, e)));
    return unsub;
  }, [id]);

  useEffect(() => {
    if (progress.done || progress.failed || progress.cancelled) {
      getRun(id).then(setRun).catch(() => {});
    }
  }, [progress.done, progress.failed, progress.cancelled, id]);

  const pipelineLabel = run ? PIPELINE_LABELS[run.pipeline_type] ?? run.pipeline_type : "";
  const active = run ? run.status === "running" || run.status === "queued" : false;
  const nodeEntries = Object.entries(progress.nodes);

  async function act(action: string, nodeId?: string, decision?: string) {
    setControlError(null);
    try {
      await controlRun(id, action, nodeId, decision);
      if (decision) setProgress((p) => ({ ...p, confirmation: null }));
      getRun(id).then(setRun).catch(() => {});
    } catch (e) {
      setControlError(String(e));
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-6">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← Dashboard
        </Link>
        <div className="mt-2 flex items-baseline justify-between">
          <h1 className="text-2xl font-bold">{run?.name ?? "Run"}</h1>
          <div className="flex items-center gap-3">
            {run && (
              <span className="text-sm text-slate-400">
                {pipelineLabel} · {run.status}
              </span>
            )}
            {active && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => act(run!.paused ? "resume" : "pause")}
                  className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700"
                >
                  {run!.paused ? "Resume" : "Pause"}
                </button>
                <button
                  onClick={() => act("cancel")}
                  className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-500"
                >
                  Cancel run
                </button>
              </div>
            )}
          </div>
        </div>
        {controlError && <p className="mt-2 text-xs text-rose-400">{controlError}</p>}
      </header>

      <div className="space-y-6">
        <ProgressPanel state={progress} />

        {nodeEntries.length > 0 && (
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Nodes</h2>
            <ul className="space-y-1 rounded-lg border border-slate-800 bg-slate-900/50 p-4 font-mono text-xs">
              {nodeEntries.map(([nodeId, node]) => (
                <li key={nodeId} className="flex items-center justify-between">
                  <span className="text-slate-300">{nodeId}</span>
                  <span className={NODE_TONE[node.status] ?? "text-slate-400"}>
                    {node.status}
                    {typeof node.kept === "number" ? ` (${node.kept})` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

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

      {progress.confirmation && (
        <ConfirmationModal
          state={progress.confirmation}
          onProceed={() => act("confirm", progress.confirmation!.node_id, "proceed")}
          onSkip={() => act("confirm", progress.confirmation!.node_id, "skip")}
          onCancel={() => act("confirm", progress.confirmation!.node_id, "cancel")}
        />
      )}
    </main>
  );
}
