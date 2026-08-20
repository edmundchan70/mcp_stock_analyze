"use client";

import type { ReactNode } from "react";

/**
 * Collapsible filter group. Controlled from the parent so active-filter chips
 * can jump to (and open) a section.
 */
export function Section({
  title,
  open,
  onToggle,
  headerExtra,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: (open: boolean) => void;
  headerExtra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel overflow-hidden">
      <button
        type="button"
        onClick={() => onToggle(!open)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-ink-850/60"
        aria-expanded={open}
      >
        <span
          className={`text-slate-600 transition-transform duration-150 ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          ▸
        </span>
        <h3 className="flex-1 text-2xs font-semibold uppercase tracking-wider text-slate-400">{title}</h3>
        {headerExtra}
      </button>
      {open && <div className="border-t border-ink-800/60 px-4 pb-4 pt-3">{children}</div>}
    </section>
  );
}
