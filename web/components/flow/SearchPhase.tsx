"use client";

import { useEffect, useMemo, useState } from "react";
import { controlRun, createRun, getRun } from "@/lib/api";
import { reportRowsFromArtifacts, searchRunBody, type FlowAction, type FlowState } from "@/lib/flow";
import type { RunTerminal, StampedRunEvent } from "@/lib/runEvents";
import type { ConfirmationState } from "@/lib/types";
import { ConfirmationModal } from "../ConfirmationModal";
import { LiveRunStatus } from "./LiveRunStatus";

export function SearchPhase({
  state,
  dispatch,
  runId,
  runTerminal,
  events,
}: {
  state: FlowState;
  dispatch: (a: FlowAction) => void;
  runId: string | null;
  runTerminal: RunTerminal;
  events: StampedRunEvent[];
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmationState | null>(null);

  const count = state.scanRows.length;
  const tavilyEstimate = count * 2; // dual-query taxonomy + leadership (VCP/BO) or catalyst+rating (EP)
  const llmCost = count * 0.02;

  // Server-side confirmation gate (fires when survivors exceed confirm_threshold).
  useEffect(() => {
    const ev = events[events.length - 1]?.event;
    if (ev?.type === "confirm_needed" && ev.node_id) {
      setConfirmation({ node_id: ev.node_id, symbol_count: ev.symbol_count ?? null, tavily_estimate: ev.tavily_estimate ?? null });
    }
  }, [events]);

  // Extract the ranked report rows once the search run completes.
  useEffect(() => {
    if (runTerminal === "succeeded" && runId) {
      getRun(runId)
        .then((r) => {
          const rows = reportRowsFromArtifacts(r.artifacts);
          dispatch({ type: "setReportRows", rows });
        })
        .catch(() => {});
    }
  }, [runTerminal, runId, dispatch]);

  async function startSearch() {
    setBusy(true);
    setError(null);
    try {
      const run = await createRun(searchRunBody(state));
      dispatch({ type: "setSearchRun", id: run.id });
      dispatch({ type: "setReportRows", rows: [] });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function act(action: string, decision?: string) {
    if (!runId || !confirmation) return;
    setError(null);
    try {
      await controlRun(runId, action, confirmation.node_id, decision);
      if (decision) setConfirmation(null);
    } catch (e) {
      setError(String(e));
    }
  }

  const running = runTerminal === "running";
  const done = runTerminal === "succeeded" && state.reportRows.length > 0;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="panel p-5">
        <h2 className="text-sm font-semibold text-slate-200">AI Search</h2>
        <p className="mt-1 text-sm text-slate-500">
          Runs the {count} survivors through the full pipeline — scanner re-run, Tavily news/context search, and LLM
          rating — then ranks the final report.
        </p>

        <div className="mt-4 grid grid-cols-3 gap-4">
          <CostStat label="Survivors" value={String(count)} />
          <CostStat label="Tavily searches" value={`≈${tavilyEstimate}`} />
          <CostStat label="Est. LLM cost" value={`$${llmCost.toFixed(2)}`} />
        </div>

        {error && <p className="mt-3 text-xs text-down-500">{error}</p>}

        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || running || count === 0}
            onClick={startSearch}
          >
            {running ? "Enriching…" : busy ? "Starting…" : `Run AI Search on ${count} symbols`}
          </button>
          {done && (
            <span className="text-xs text-up-500">Enrichment complete — {state.reportRows.length} rows ranked.</span>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-600">
          {count > 50
            ? "Large batch — the run will pause and ask you to confirm before any Tavily calls."
            : "Per-symbol status streams into the live status panel below as enrichment runs."}
        </p>
      </section>

      {runId && runTerminal !== "idle" && <LiveRunStatus runId={runId} events={events} runTerminal={runTerminal} />}

      {confirmation && (
        <ConfirmationModal
          state={confirmation}
          onProceed={() => act("confirm", "proceed")}
          onSkip={() => act("confirm", "skip")}
          onCancel={() => act("confirm", "cancel")}
        />
      )}
    </div>
  );
}

function CostStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-ink-800 bg-ink-850 px-3 py-2">
      <div className="text-2xs uppercase tracking-wider text-slate-600">{label}</div>
      <div className="tnum mt-0.5 font-mono text-lg text-slate-200">{value}</div>
    </div>
  );
}
