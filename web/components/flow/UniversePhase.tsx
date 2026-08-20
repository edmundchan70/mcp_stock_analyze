"use client";

import { useEffect, useMemo, useState } from "react";
import { previewRun } from "@/lib/api";
import {
  buildScannerGraph,
  FAMILY_LABELS,
  FAMILY_PIPELINES,
  parseSymbolText,
  type FlowAction,
  type FlowState,
} from "@/lib/flow";

export function UniversePhase({
  state,
  dispatch,
}: {
  state: FlowState;
  dispatch: (a: FlowAction) => void;
}) {
  const [estimate, setEstimate] = useState<{
    symbols: number;
    duration: string;
    seconds: number;
    cost: number;
    warnings: string[];
  } | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const symbols = useMemo(() => parseSymbolText(state.universeText), [state.universeText]);

  useEffect(() => {
    if (state.universeSource === "paste" && symbols.length === 0) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      setEstimating(true);
      setPreviewError(null);
      previewRun({
        name: state.runName,
        pipeline_type: FAMILY_PIPELINES[state.family],
        graph: buildScannerGraph(state.family, state.scannerVars),
        universe_source: state.universeSource,
        force_symbols: state.universeSource === "snapshot" ? "" : state.universeText,
      })
        .then((res) => {
          if (cancelled) return;
          setEstimate(res.estimate);
        })
        .catch((e) => {
          if (cancelled) return;
          setPreviewError(String(e));
        })
        .finally(() => {
          if (!cancelled) setEstimating(false);
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.universeSource, state.universeText, state.family, state.runName]);

  const sourceIsSweep = state.universeSource === "snapshot";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="panel p-5">
        <h2 className="text-sm font-semibold text-slate-200">Universe</h2>
        <p className="mt-1 text-sm text-slate-500">
          Define the symbol set that feeds the scanner. Paste a watchlist, or sweep the whole
          US market (expensive — BO presets only).
        </p>

        <div className="mt-4 flex items-center gap-1 rounded-md border border-ink-700 bg-ink-800/60 p-1">
          {(
            [
              ["paste", "Paste symbols"],
              ["snapshot", "Market sweep"],
            ] as const
          ).map(([src, label]) => (
            <button
              key={src}
              type="button"
              onClick={() => {
                dispatch({ type: "setUniverseSource", source: src });
                clearResults(dispatch);
              }}
              className={`flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors duration-150 ${
                state.universeSource === src
                  ? "bg-accent-600 text-ink-950"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {sourceIsSweep ? (
          <div className="mt-4 space-y-3">
            <div className="rounded-md border border-accent-700/40 bg-accent-600/5 px-4 py-3 text-sm text-slate-400">
              <span className="font-medium text-accent-400">Snapshot sweep</span> — resolves every
              liquid US ticker via Polygon, prefilters by price/liquidity, then runs the{" "}
              <span className="text-slate-200">{FAMILY_LABELS[state.family]}</span> scanner over
              the survivors. Estimate below is nominal (~3,000 candidates).
            </div>
            <p className="text-xs text-slate-600">
              {state.family === "bo"
                ? "The daily BO preset runs this way by default."
                : state.family === "premarket"
                  ? "Premarket grep sweeps the snapshot first, then unions any pasted symbols (capped)."
                  : "Sweeps are unusual for EP/VCP — a pasted watchlist is typically the right universe."}
            </p>
          </div>
        ) : (
          <div className="mt-4">
            <label className="label" htmlFor="universe-text">
              Symbols
            </label>
            <textarea
              id="universe-text"
              className="field min-h-[120px] font-mono text-sm"
              placeholder={"AAPL, MSFT\nNVDA  TSLA  META\nor paste anything messy — the server parses it"}
              value={state.universeText}
              onChange={(e) => {
                dispatch({ type: "setUniverseText", text: e.target.value });
                clearResults(dispatch);
              }}
              spellCheck={false}
            />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {symbols.length === 0 ? (
                <span className="text-xs text-slate-600">no clean tickers parsed yet</span>
              ) : (
                symbols.map((s) => (
                  <span
                    key={s}
                    className="rounded border border-ink-700 bg-ink-800 px-2 py-0.5 font-mono text-xs text-slate-300"
                  >
                    {s}
                  </span>
                ))
              )}
            </div>
          </div>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">Cost preview</h3>
          {estimating && <span className="text-2xs text-slate-600">estimating…</span>}
        </div>
        {previewError ? (
          <p className="mt-2 text-xs text-down-500">{previewError}</p>
        ) : estimate ? (
          <div className="mt-3 grid grid-cols-3 gap-4">
            <Stat label="Symbols" value={estimate.symbols.toLocaleString()} />
            <Stat label="Est. duration" value={estimate.duration} />
            <Stat label="Est. cost" value={`$${estimate.cost.toFixed(2)}`} />
            {estimate.warnings.map((w) => (
              <p key={w} className="col-span-3 text-xs text-amber-300">
                ⚠ {w}
              </p>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs text-slate-600">
            {state.universeSource === "paste"
              ? "Paste symbols to see a cost estimate before you run."
              : "The sweep estimate appears automatically."}
          </p>
        )}
      </section>

      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-600">
          Scanner family: <span className="text-slate-300">{FAMILY_LABELS[state.family]}</span> —
          switch it in the Scanner phase.
        </p>
        <button
          type="button"
          className="btn-primary"
          disabled={symbols.length === 0 && !sourceIsSweep}
          onClick={() => dispatch({ type: "setPhase", phase: 2 })}
        >
          Continue → Scanner
        </button>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-ink-800 bg-ink-850 px-3 py-2">
      <div className="text-2xs uppercase tracking-wider text-slate-600">{label}</div>
      <div className="tnum mt-0.5 font-mono text-lg text-slate-200">{value}</div>
    </div>
  );
}

function clearResults(dispatch: (a: FlowAction) => void) {
  dispatch({ type: "setScanRun", id: null });
  dispatch({ type: "setScanRows", rows: [] });
  dispatch({ type: "setSearchRun", id: null });
  dispatch({ type: "setReportRows", rows: [] });
}
