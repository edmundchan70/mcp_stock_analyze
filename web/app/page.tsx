"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RunTable } from "@/components/RunTable";
import { listRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

export default function Home() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Stock Scan Dashboard</h1>
          <p className="text-sm text-slate-400">Episodic Pivot · VCP · Qullamaggie BO</p>
        </div>
        <Link
          href="/new"
          className="rounded-md bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500"
        >
          New scan
        </Link>
      </header>

      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : error ? (
        <p className="text-rose-400">{error}</p>
      ) : (
        <RunTable runs={runs} />
      )}
    </main>
  );
}
