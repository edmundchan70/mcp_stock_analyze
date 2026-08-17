"use client";

import { useState } from "react";
import type { PipelineType } from "@/lib/types";

export interface ScanFormValues {
  name: string;
  pipeline_type: PipelineType;
  force_symbols: string;
  use_screener: boolean;
  select: string;
  run_catalyst: boolean;
  apply_gates: boolean;
  bo_profile: string;
}

const PIPELINE_OPTIONS: { value: PipelineType; label: string }[] = [
  { value: "daily_bo_scan", label: "Qullamaggie BO" },
  { value: "daily_vcp_scan", label: "VCP" },
  { value: "daily_ep_scan", label: "Episodic Pivot (EP)" },
];

const BO_PROFILES = [
  { value: "best", label: "Best (ADV $50M / EMA 5% / Base 40d)" },
  { value: "moderate-lose", label: "Moderate lose (loosen EMA)" },
  { value: "widen", label: "Widen (lower liquidity floor)" },
];

export function ScanForm({ onSubmit, submitting }: { onSubmit: (v: ScanFormValues) => void; submitting: boolean }) {
  const [name, setName] = useState("scan");
  const [pipelineType, setPipelineType] = useState<PipelineType>("daily_bo_scan");
  const [forceSymbols, setForceSymbols] = useState("");
  const [universe, setUniverse] = useState<"paste" | "sweep">("paste");
  const [select, setSelect] = useState("strict");
  const [runCatalyst, setRunCatalyst] = useState(true);
  const [applyGates, setApplyGates] = useState(true);
  const [boProfile, setBoProfile] = useState("best");
  const [error, setError] = useState<string | null>(null);

  const isSweep = pipelineType === "daily_bo_scan" && universe === "sweep";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isSweep && !forceSymbols.trim()) {
      setError("Paste at least one ticker.");
      return;
    }
    setError(null);
    onSubmit({
      name,
      pipeline_type: pipelineType,
      force_symbols: isSweep ? "" : forceSymbols,
      use_screener: isSweep,
      select,
      run_catalyst: runCatalyst,
      apply_gates: applyGates,
      bo_profile: boProfile,
    });
  }

  const field =
    "w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none";
  const label = "mb-1 block text-sm font-medium text-slate-400";

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className={label} htmlFor="pipeline">Pipeline</label>
        <select
          id="pipeline"
          className={field}
          value={pipelineType}
          onChange={(e) => setPipelineType(e.target.value as PipelineType)}
        >
          {PIPELINE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className={label} htmlFor="name">Run name</label>
        <input id="name" className={field} value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      {pipelineType === "daily_bo_scan" && (
        <div>
          <label className={label} htmlFor="universe">Universe</label>
          <select
            id="universe"
            className={field}
            value={universe}
            onChange={(e) => setUniverse(e.target.value as "paste" | "sweep")}
          >
            <option value="paste">Paste symbols</option>
            <option value="sweep">Full market sweep</option>
          </select>
        </div>
      )}

      {!isSweep && (
        <div>
          <label className={label} htmlFor="symbols">Symbols (paste list)</label>
          <textarea
            id="symbols"
            className={`${field} min-h-[96px] font-mono`}
            placeholder="AAPL, MSFT, TSLA"
            value={forceSymbols}
            onChange={(e) => setForceSymbols(e.target.value)}
          />
        </div>
      )}

      {pipelineType === "daily_ep_scan" && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={label} htmlFor="select">Gate bucket</label>
            <select id="select" className={field} value={select} onChange={(e) => setSelect(e.target.value)}>
              <option value="strict">Strict</option>
              <option value="baseline">Baseline</option>
              <option value="both">Both</option>
            </select>
          </div>
          <label className="flex items-center gap-2 pt-6 text-sm text-slate-300">
            <input type="checkbox" checked={runCatalyst} onChange={(e) => setRunCatalyst(e.target.checked)} />
            Run catalyst + rating
          </label>
        </div>
      )}

      {(pipelineType === "daily_vcp_scan" || pipelineType === "daily_bo_scan") && (
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={applyGates} onChange={(e) => setApplyGates(e.target.checked)} />
          Apply gates
        </label>
      )}

      {pipelineType === "daily_bo_scan" && (
        <div>
          <label className={label} htmlFor="profile">Funnel profile</label>
          <select id="profile" className={field} value={boProfile} onChange={(e) => setBoProfile(e.target.value)}>
            {BO_PROFILES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {error && <p className="text-sm text-rose-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-cyan-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
      >
        {submitting ? "Starting…" : "Run scan"}
      </button>
    </form>
  );
}
