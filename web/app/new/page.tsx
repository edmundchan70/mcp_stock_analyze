"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ScanForm, type ScanFormValues } from "@/components/ScanForm";
import { createRun } from "@/lib/api";

export default function NewScan() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(values: ScanFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun({ ...values });
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <header className="mb-8">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-bold">New scan</h1>
      </header>

      {error && (
        <p className="mb-4 rounded-md border border-rose-800 bg-rose-900/30 px-4 py-3 text-sm text-rose-300">
          {error}
        </p>
      )}

      <ScanForm onSubmit={handleSubmit} submitting={submitting} />
    </main>
  );
}
