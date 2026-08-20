"use client";

import type { ReactNode } from "react";

/** A filter row: label + control + unit suffix + reset-to-default dot. */
export function FilterRow({
  label,
  control,
  unit,
  dirty,
  onReset,
}: {
  label: string;
  control: ReactNode;
  unit?: string;
  /** True when the current value differs from the default — shows the reset dot. */
  dirty?: boolean;
  onReset?: () => void;
}) {
  return (
    <div className="group flex items-center gap-2">
      <div className="min-w-0 flex-1">
        <label className="mb-1 block truncate text-2xs font-medium text-slate-400">{label}</label>
        <div className="flex items-center gap-1.5">
          <div className="min-w-0 flex-1">{control}</div>
          {unit && <span className="shrink-0 font-mono text-2xs text-slate-600">{unit}</span>}
        </div>
      </div>
      {dirty && onReset && (
        <button
          type="button"
          onClick={onReset}
          title="Reset to default"
          aria-label={`Reset ${label}`}
          className="mt-4 shrink-0 rounded-full p-1 text-slate-600 transition-colors hover:bg-ink-700 hover:text-slate-300"
        >
          <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3.5 3.5v3h3M12.5 12.5v-3h-3" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4.1 10a5 5 0 0 0 8.4 1M11.9 6a5 5 0 0 0-8.4-1" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </div>
  );
}
