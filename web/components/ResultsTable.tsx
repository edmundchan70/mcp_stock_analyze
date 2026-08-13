"use client";

import { StarBadge } from "./StarBadge";
import type { RatedStock } from "@/lib/types";

function isEpShape(stock: RatedStock): boolean {
  return typeof stock.ep_rating === "number";
}

function collectRatedStocks(artifacts: Record<string, unknown>): RatedStock[] {
  const agent3 = artifacts["agent3"] as { stocks?: RatedStock[] } | undefined;
  return agent3?.stocks ?? [];
}

export function ResultsTable({
  artifacts,
  pipelineType,
}: {
  artifacts: Record<string, unknown>;
  pipelineType: string;
}) {
  const stocks = collectRatedStocks(artifacts);
  if (stocks.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-center text-sm text-slate-400">
        No rated stocks in this run{artifacts["agent1"] ? "" : " (Agent 1 produced no survivors)"}.
      </div>
    );
  }

  const ep = isEpShape(stocks[0]);

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-400">
          <tr>
            <th className="px-4 py-3 font-medium">Rating</th>
            <th className="px-4 py-3 font-medium">Symbol</th>
            {ep ? (
              <>
                <th className="px-4 py-3 font-medium">Catalyst</th>
                <th className="px-4 py-3 font-medium">Rationale</th>
              </>
            ) : (
              <>
                <th className="px-4 py-3 font-medium">Variant</th>
                <th className="px-4 py-3 font-medium">Sector</th>
                <th className="px-4 py-3 font-medium">Group</th>
                <th className="px-4 py-3 font-medium">Capped</th>
              </>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {stocks.map((s) => (
            <tr key={s.symbol} className="hover:bg-slate-900/40">
              <td className="px-4 py-3">
                <StarBadge rating={(s.ep_rating ?? s.final_rating ?? 0)} />
              </td>
              <td className="px-4 py-3 font-semibold text-slate-100">{s.symbol}</td>
              {ep ? (
                <>
                  <td className="px-4 py-3 text-slate-300">{s.catalyst_type ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-400">{s.ep_rationale ?? "—"}</td>
                </>
              ) : (
                <>
                  <td className="px-4 py-3 text-slate-300">{s.variant ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{s.sector ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{s.industry_group_strength_flag ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-400">{s.cap_applied ? "yes" : "no"}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-slate-800 px-4 py-2 text-xs text-slate-500">
        {pipelineType} · {stocks.length} rated
      </p>
    </div>
  );
}
