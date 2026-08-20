"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  clearFlowDraft,
  FAMILY_HAS_SEARCH,
  FAMILY_LABELS,
  rowRating,
  type FlowAction,
  type FlowState,
} from "@/lib/flow";

export function ReportPhase({ state, dispatch }: { state: FlowState; dispatch: (a: FlowAction) => void }) {
  const [sortDesc, setSortDesc] = useState(true);
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toUpperCase();
    const filtered = q
      ? state.reportRows.filter((r) => String(r.symbol ?? "").toUpperCase().includes(q))
      : state.reportRows;
    const dir = sortDesc ? -1 : 1;
    return [...filtered].sort((a, b) => (rowRating(a) - rowRating(b)) * dir || String(a.symbol).localeCompare(String(b.symbol)));
  }, [state.reportRows, query, sortDesc]);

  function handleReset() {
    clearFlowDraft();
    dispatch({ type: "reset" });
  }

  const ep = state.family === "ep";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Final report — {FAMILY_LABELS[state.family]}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {FAMILY_HAS_SEARCH[state.family]
                ? `${state.reportRows.length} ranked row${state.reportRows.length === 1 ? "" : "s"} after AI enrichment and down-only caps.`
                : `${state.reportRows.length} ranked row${state.reportRows.length === 1 ? "" : "s"} from the scanner bucket — no AI enrichment for this family.`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {state.searchRunId && (
              <Link href={`/runs/${state.searchRunId}`} className="btn-ghost">
                Run detail ↗
              </Link>
            )}
            <button type="button" className="btn-ghost" onClick={() => exportJson(state.reportRows, state.runName)}>
              Export JSON
            </button>
            <button type="button" className="btn-ghost" onClick={() => exportCsv(state.reportRows, state.runName)}>
              Export CSV
            </button>
            <button type="button" className="btn-primary" onClick={handleReset}>
              New scan
            </button>
          </div>
        </div>
        <input
          className="field mt-4 w-64 px-2.5 py-1.5 font-mono text-sm"
          placeholder="Search symbol…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </section>

      {state.reportRows.length === 0 ? (
        <section className="panel flex flex-col items-center gap-2 p-12 text-center">
          <p className="text-sm text-slate-500">No report rows yet.</p>
          <p className="text-xs text-slate-600">
            {FAMILY_HAS_SEARCH[state.family]
              ? "Run AI Search to produce the ranked report."
              : "Run the scanner to produce the ranked report."}
          </p>
        </section>
      ) : (
        <section className="panel overflow-hidden">
          <div className="max-h-[60vh] overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-ink-900 text-2xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">
                    <button type="button" className="hover:text-slate-300" onClick={() => setSortDesc((d) => !d)}>
                      Rating {sortDesc ? "↓" : "↑"}
                    </button>
                  </th>
                  <th className="px-4 py-2.5 font-medium">Symbol</th>
                  {ep ? (
                    <>
                      <th className="px-4 py-2.5 font-medium">Catalyst</th>
                      <th className="px-4 py-2.5 font-medium">Rationale</th>
                    </>
                  ) : (
                    <>
                      <th className="px-4 py-2.5 font-medium">Variant</th>
                      <th className="px-4 py-2.5 font-medium">Sector</th>
                      <th className="px-4 py-2.5 font-medium">Group</th>
                      <th className="px-4 py-2.5 font-medium">Capped</th>
                    </>
                  )}
                  <th className="px-4 py-2.5 font-medium">Context</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800/60">
                {rows.map((r) => {
                  const symbol = String(r.symbol ?? "");
                  return (
                    <tr key={symbol} className="hover:bg-ink-850/60">
                      <td className="px-4 py-2.5 font-mono text-accent-400">{stars(rowRating(r))}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono font-semibold text-slate-100">{symbol}</td>
                      {ep ? (
                        <>
                          <td className="px-4 py-2.5 text-slate-300">{String(r.catalyst_type ?? "—")}</td>
                          <td className="max-w-[280px] px-4 py-2.5 text-xs text-slate-500">
                            <span className="line-clamp-2">{String(r.ep_rationale ?? "—")}</span>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-4 py-2.5 text-slate-300">{String(r.variant ?? r.setup_variant ?? "—")}</td>
                          <td className="px-4 py-2.5 text-slate-300">
                            {String(deep(r, "enrichment.sector") ?? r.sector ?? "—")}
                          </td>
                          <td className="px-4 py-2.5 text-slate-300">
                            {String(
                              deep(r, "enrichment.industry_group_strength_flag") ??
                                r.industry_group_strength_flag ??
                                "—",
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-slate-400">{r.cap_applied ? "yes" : "no"}</td>
                        </>
                      )}
                      <td className="max-w-[240px] px-4 py-2.5 text-xs text-slate-500">
                        {String(
                          r.market_leadership_context ??
                            r.growth_catalysts ??
                            r.catalyst_summary ??
                            deep(r, "enrichment.market_leadership_context") ??
                            "—",
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-ink-800 px-4 py-2 font-mono text-2xs text-slate-600">
            {rows.length} / {state.reportRows.length} rows · sorted by rating
          </p>
        </section>
      )}
    </div>
  );
}

function stars(rating: number): string {
  return "★".repeat(Math.max(0, Math.min(5, Math.round(rating)))) || "—";
}

/** Deep, null-safe read of a dotted path on an arbitrary row. */
function deep(row: Record<string, unknown>, path: string): unknown {
  let cur: unknown = row;
  for (const part of path.split(".")) {
    if (cur === null || cur === undefined || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function download(name: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportJson(rows: Record<string, unknown>[], name: string): void {
  download(`${name || "report"}-report.json`, JSON.stringify(rows, null, 2), "application/json");
}

export function exportCsv(rows: Record<string, unknown>[], name: string): void {
  if (rows.length === 0) return;
  const keys: string[] = [];
  for (const r of rows) {
    for (const k of Object.keys(r)) if (!keys.includes(k)) keys.push(k);
  }
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  const lines = [keys.map(esc).join(","), ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))];
  download(`${name || "report"}-report.csv`, "\uFEFF" + lines.join("\n"), "text/csv;charset=utf-8");
}
