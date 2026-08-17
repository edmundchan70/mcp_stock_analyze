"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RunTable } from "@/components/RunTable";
import { listRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const SETTLED = new Set(["succeeded", "failed", "cancelled"]);

export default function Home() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listRuns()
      .then((rs) => {
        setRuns(rs);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // Poll every 5s while any run is in flight; stop once all runs are settled.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = () => {
      listRuns()
        .then((rs) => {
          if (cancelled) return;
          setRuns(rs);
          setLoading(false);
          const allSettled = rs.every((r) => SETTLED.has(r.status));
          if (!allSettled) {
            timer = setTimeout(load, 5000);
          }
        })
        .catch((e) => {
          if (cancelled) return;
          setError(String(e));
          setLoading(false);
        });
    };

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Stock Scan Dashboard</h1>
          <p className="text-sm text-slate-400">Episodic Pivot · VCP · Qullamaggie BO</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/editor"
            className="rounded-md bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-700"
          >
            Graph editor
          </Link>
          <Link
            href="/new"
            className="rounded-md bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500"
          >
            New scan
          </Link>
        </div>
      </header>

      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : error ? (
        <p className="text-rose-400">{error}</p>
      ) : (
        <RunTable runs={runs} onChanged={refresh} />
      )}
    </main>
  );
}
