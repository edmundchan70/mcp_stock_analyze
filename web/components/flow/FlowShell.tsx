"use client";

import { useEffect, useReducer, useState } from "react";
import Link from "next/link";
import {
  activeRunId,
  FAMILY_LABELS,
  flowReducer,
  initialFlowState,
  loadFlowDraft,
  phaseDone,
  phaseLocked,
  phasesForFamily,
  saveFlowDraft,
} from "@/lib/flow";
import { useRunEvents } from "@/lib/runEvents";
import { ActivityFeed } from "./ActivityFeed";
import { PatternPhase } from "./PatternPhase";
import { PhaseStepper } from "./PhaseStepper";
import { ReportPhase } from "./ReportPhase";
import { ScannerPhase } from "./ScannerPhase";
import { SearchPhase } from "./SearchPhase";
import { UniversePhase } from "./UniversePhase";

export function FlowShell() {
  const [state, dispatch] = useReducer(flowReducer, undefined, initialFlowState);
  const [hydrated, setHydrated] = useState(false);

  // Hydrate the persisted draft once on the client (avoids SSR mismatch).
  useEffect(() => {
    const draft = loadFlowDraft();
    if (draft) dispatch({ type: "hydrate", state: draft });
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) saveFlowDraft(state);
  }, [state, hydrated]);

  const runId = activeRunId(state);
  const { events, terminal, error } = useRunEvents(runId);

  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b border-ink-800 bg-ink-900/70">
        <div className="flex items-center gap-4 px-5 py-2.5">
          <Link href="/" className="flex items-center gap-2 text-accent-500" title="Dashboard">
            <span className="text-lg leading-none">◤</span>
          </Link>
          <div className="min-w-0">
            <input
              className="w-60 bg-transparent font-mono text-sm font-semibold text-slate-100 focus:outline-none"
              value={state.runName}
              onChange={(e) => dispatch({ type: "setRunName", name: e.target.value })}
              title="Run name"
            />
            <div className="text-2xs uppercase tracking-widest text-slate-600">run name</div>
          </div>
          <span className="rounded border border-ink-700 bg-ink-800/60 px-2 py-0.5 font-mono text-xs text-accent-400">
            {FAMILY_LABELS[state.family]}
          </span>
          <div className="ml-auto flex items-center gap-3">
            {state.phase === 2 && state.scanRows.length > 0 && (
              <span className="font-mono text-xs text-slate-500">{state.scanRows.length} survivors</span>
            )}
            {state.phase === 5 && state.reportRows.length > 0 && (
              <span className="font-mono text-xs text-slate-500">{state.reportRows.length} reported</span>
            )}
            {runId && (
              <Link
                href={`/runs/${runId}`}
                className="rounded border border-ink-700 px-2 py-0.5 font-mono text-2xs text-slate-500 hover:text-slate-300"
                title="Open run detail"
              >
                {runId.slice(0, 8)} ↗
              </Link>
            )}
          </div>
        </div>
        <div className="border-t border-ink-800/60 px-5 py-2">
          <PhaseStepper
            current={state.phase}
            phases={phasesForFamily(state.family)}
            isLocked={(p) => phaseLocked(state, p)}
            isDone={(p) => phaseDone(state, p)}
            onSelect={(p) => dispatch({ type: "setPhase", phase: p })}
          />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto p-6">
          {state.phase === 1 && <UniversePhase state={state} dispatch={dispatch} />}
          {state.phase === 2 && (
            <ScannerPhase
              state={state}
              dispatch={dispatch}
              runId={state.scanRunId}
              runTerminal={runId === state.scanRunId ? terminal : "idle"}
              events={runId === state.scanRunId ? events : []}
            />
          )}
          {state.phase === 3 && <PatternPhase state={state} />}
          {state.phase === 4 && (
            <SearchPhase
              state={state}
              dispatch={dispatch}
              runId={state.searchRunId}
              runTerminal={runId === state.searchRunId ? terminal : "idle"}
              events={runId === state.searchRunId ? events : []}
            />
          )}
          {state.phase === 5 && <ReportPhase state={state} dispatch={dispatch} />}
        </main>
        <ActivityFeed runId={runId} events={events} terminal={terminal} error={error} />
      </div>
    </div>
  );
}
