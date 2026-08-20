"use client";

import { useMemo, useState } from "react";
import { fetchOhlcv } from "@/lib/api";
import {
  FAMILY_LABELS,
  patternOverlay,
  rowExplanation,
  rowRating,
  type FlowState,
} from "@/lib/flow";
import type { OhlcvBar } from "@/lib/types";
import { ChartCard } from "./ChartCard";

const GALLERY_CAP = 60;

export function PatternPhase({ state }: { state: FlowState }) {
  const [charts, setCharts] = useState<Record<string, OhlcvBar[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buckets = useMemo(() => {
    const counts = { 5: 0, 4: 0, 3: 0 };
    for (const r of state.scanRows) {
      const rating = rowRating(r);
      if (rating >= 5) counts[5] += 1;
      else if (rating >= 4) counts[4] += 1;
      else if (rating >= 3) counts[3] += 1;
    }
    return counts;
  }, [state.scanRows]);

  const galleryRows = useMemo(() => {
    const sorted = [...state.scanRows].sort((a, b) => rowRating(b) - rowRating(a));
    return sorted.slice(0, GALLERY_CAP);
  }, [state.scanRows]);

  const hidden = state.scanRows.length - galleryRows.length;

  async function loadEvidence() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOhlcv(
        state.scanRows.map((r) => ({ symbol: String(r.symbol), exchange: String(r.exchange ?? "NASDAQ") })),
        300,
      );
      setCharts(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Detection summary */}
      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Pattern detection — {FAMILY_LABELS[state.family]}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {state.scanRows.length} survivor{state.scanRows.length === 1 ? "" : "s"} detected automatically by the
              scanner. Charts below are evidence — everything here flows to AI Search as-is.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <BucketBadge stars={5} count={buckets[5]} />
            <BucketBadge stars={4} count={buckets[4]} />
            <BucketBadge stars={3} count={buckets[3]} />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            className="btn-primary"
            disabled={loading || state.scanRows.length === 0}
            onClick={loadEvidence}
          >
            {loading ? "Fetching OHLCV…" : Object.keys(charts).length > 0 ? "Refresh evidence" : `Load chart evidence (${state.scanRows.length} symbols)`}
          </button>
          {hidden > 0 && (
            <span className="text-xs text-slate-600">Gallery capped at {GALLERY_CAP} for performance — {hidden} more.</span>
          )}
          {error && <span className="text-xs text-down-500">{error}</span>}
        </div>
      </section>

      {/* Chart evidence gallery */}
      {Object.keys(charts).length > 0 ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
          {galleryRows
            .filter((r) => charts[String(r.symbol).toUpperCase()])
            .map((r) => {
              const symbol = String(r.symbol).toUpperCase();
              const bars = charts[symbol] ?? [];
              const overlay = patternOverlay(state.family, r, bars);
              return (
                <ChartCard
                  key={symbol}
                  symbol={symbol}
                  bars={bars}
                  overlay={overlay}
                  footer={
                    <div className="border-t border-ink-800 px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm font-semibold text-slate-100">{symbol}</span>
                        <span className="font-mono text-xs text-accent-400">{stars(rowRating(r))}</span>
                      </div>
                      <ul className="mt-1.5 space-y-0.5 text-2xs leading-snug text-slate-500">
                        {rowExplanation(state.family, r).map((line, i) => (
                          <li key={i} className="truncate" title={line}>
                            {line}
                          </li>
                        ))}
                      </ul>
                    </div>
                  }
                />
              );
            })}
        </div>
      ) : (
        <section className="panel flex flex-col items-center justify-center gap-2 p-12 text-center">
          <p className="text-sm text-slate-500">No chart evidence loaded yet.</p>
          <p className="text-xs text-slate-600">
            Load daily OHLCV for the {state.scanRows.length} survivors and review what the {FAMILY_LABELS[state.family]}{" "}
            detector actually saw.
          </p>
        </section>
      )}

      <div className="flex items-center justify-between rounded-md border border-accent-700/30 bg-accent-600/5 px-4 py-3">
        <p className="text-sm text-slate-400">
          <span className="font-medium text-accent-400">No gate here.</span> Every survivor proceeds to AI Search —
          this phase is for understanding, not deciding.
        </p>
        <span className="hidden font-mono text-xs text-slate-600 sm:block">evidence-only · {state.scanRows.length} → AI Search</span>
      </div>
    </div>
  );
}

function BucketBadge({ stars: s, count }: { stars: number; count: number }) {
  return (
    <div className="rounded border border-ink-700 bg-ink-850 px-2.5 py-1.5 text-center">
      <div className="text-sm font-bold text-accent-400">{"★".repeat(s)}</div>
      <div className="tnum text-2xs text-slate-500">{count}</div>
    </div>
  );
}

function stars(rating: number): string {
  return "★".repeat(Math.max(0, Math.min(5, Math.round(rating)))) || "—";
}
