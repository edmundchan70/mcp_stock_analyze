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
        <div className="flex items-center gap-4">
          <span className="text-2xl text-accent-500">◤</span>
          <div>
            <h1 className="font-mono text-xl font-bold tracking-tight text-slate-100">Scan Desk</h1>
            <p className="text-xs uppercase tracking-widest text-slate-500">EP · VCP · Qullamaggie BO</p>
          </div>
        </div>
        <Link href="/flow" className="btn-primary">
          New guided scan
        </Link>
      </header>

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-down-500">{error}</p>
      ) : (
        <RunTable runs={runs} onChanged={refresh} />
      )}
    </main>
  );
}
