"use client";

import type { PhaseId } from "@/lib/flow";
import { PHASES } from "@/lib/flow";

export function PhaseStepper({
  current,
  phases,
  isLocked,
  isDone,
  onSelect,
}: {
  current: PhaseId;
  phases?: PhaseId[];
  isLocked: (p: PhaseId) => boolean;
  isDone: (p: PhaseId) => boolean;
  onSelect: (p: PhaseId) => void;
}) {
  const visible = phases ?? PHASES.map((p) => p.id);
  const items = PHASES.filter((p) => visible.includes(p.id));
  return (
    <nav className="flex items-center">
      <ol className="flex items-center gap-0.5">
        {items.map((p, i) => {
          const active = p.id === current;
          const locked = isLocked(p.id);
          const done = isDone(p.id) && !active;
          const tone = active
            ? "bg-accent-600 text-ink-950"
            : done
              ? "border border-accent-700/60 bg-accent-600/10 text-accent-400"
              : "border border-ink-700 bg-ink-800/60 text-slate-500";
          return (
            <li key={p.id} className="flex items-center">
              <button
                type="button"
                onClick={() => !locked && onSelect(p.id)}
                disabled={locked}
                title={`${p.id}. ${p.label} — ${p.caption}`}
                className={`group flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium transition-colors duration-150 ${
                  locked ? "cursor-not-allowed opacity-60" : "hover:border-ink-600"
                }`}
              >
                <span
                  className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold tnum ${tone}`}
                >
                  {done ? "✓" : p.id}
                </span>
                <span
                  className={`hidden lg:inline ${active ? "text-accent-500" : done ? "text-slate-300" : "text-slate-500"}`}
                >
                  {p.label}
                </span>
              </button>
              {i < items.length - 1 && <span className="h-px w-3 bg-ink-700 sm:w-5" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
