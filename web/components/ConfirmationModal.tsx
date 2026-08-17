"use client";

import type { ConfirmationState } from "@/lib/types";

export function ConfirmationModal({
  state,
  onProceed,
  onSkip,
  onCancel,
}: {
  state: ConfirmationState;
  onProceed: () => void;
  onSkip: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-6">
      <div className="w-full max-w-md rounded-lg border border-amber-500/50 bg-slate-900 p-5">
        <h2 className="text-sm font-semibold text-amber-300">AI Search confirmation</h2>
        <p className="mt-2 text-sm text-slate-300">
          Node <span className="font-mono text-slate-100">{state.node_id}</span> is about to run
          AI enrichment on{" "}
          <span className="font-semibold text-slate-100">{state.symbol_count ?? 0}</span> symbols
          (≈{state.tavily_estimate ?? 0} Tavily calls). This may take a while and incur cost.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-500"
          >
            Cancel run
          </button>
          <button
            onClick={onSkip}
            className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700"
          >
            Skip node
          </button>
          <button
            onClick={onProceed}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500"
          >
            Proceed
          </button>
        </div>
      </div>
    </div>
  );
}
