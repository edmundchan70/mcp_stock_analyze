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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/85 p-6 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-md border border-accent-700/50 bg-ink-900 p-5 shadow-2xl shadow-black/50">
        <h2 className="text-sm font-semibold text-accent-400">AI Search confirmation</h2>
        <p className="mt-2 text-sm text-slate-400">
          Node <span className="font-mono text-slate-100">{state.node_id}</span> is about to run AI enrichment on{" "}
          <span className="font-semibold text-slate-100">{state.symbol_count ?? 0}</span> symbols
          (≈{state.tavily_estimate ?? 0} Tavily calls). This may take a while and incur cost.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="btn-danger px-3 py-1.5 text-sm">
            Cancel run
          </button>
          <button onClick={onSkip} className="btn-ghost px-3 py-1.5 text-sm">
            Skip node
          </button>
          <button onClick={onProceed} className="btn-primary px-3 py-1.5 text-sm">
            Proceed
          </button>
        </div>
      </div>
    </div>
  );
}
