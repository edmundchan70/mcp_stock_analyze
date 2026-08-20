"use client";

/** Row container for active-filter chips (TradingView-screener style). */
export function ChipRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-ink-800/60 px-4 py-2">
      <span className="text-2xs font-semibold uppercase tracking-wider text-slate-600">Active filters</span>
      {children}
    </div>
  );
}
