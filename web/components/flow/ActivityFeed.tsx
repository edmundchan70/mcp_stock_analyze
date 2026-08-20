"use client";

import { useEffect, useRef, useState } from "react";
import type { RunEvent } from "@/lib/types";
import type { RunTerminal, StampedRunEvent } from "@/lib/runEvents";

interface FeedLine {
  text: string;
  tone: string;
}

const TONES = {
  stage: "text-slate-300",
  stageDone: "text-accent-400",
  fail: "text-down-500",
  console: "text-slate-500",
  nodeOk: "text-up-500",
  nodeErr: "text-down-500",
  nodeSkip: "text-slate-500",
  nodeRun: "text-slate-400",
  confirm: "text-accent-300",
  control: "text-slate-400",
  terminal: "text-slate-200",
  warn: "text-amber-300",
};

function feedLine(e: RunEvent): FeedLine {
  switch (e.type) {
    case "stage":
      return { text: e.text ?? "", tone: TONES.stage };
    case "stage_done":
      return { text: `✓ ${e.text ?? ""}`, tone: TONES.stageDone };
    case "fail":
      return { text: `✗ ${e.text ?? ""}`, tone: TONES.fail };
    case "console":
      return { text: e.text ?? "", tone: TONES.console };
    case "node": {
      const status = e.status ?? "running";
      const tone =
        status === "ok" ? TONES.nodeOk : status === "error" || status === "cancelled" ? TONES.nodeErr : status === "skipped" ? TONES.nodeSkip : TONES.nodeRun;
      const kept = typeof e.kept === "number" ? ` · kept ${e.kept}` : "";
      return { text: `node ${e.node_id ?? ""} [${e.tool_id ?? ""}] ${status}${kept}`, tone };
    }
    case "confirm_needed":
      return {
        text: `⚠ confirmation — ${e.symbol_count ?? 0} symbols, ≈${e.tavily_estimate ?? 0} Tavily calls`,
        tone: TONES.confirm,
      };
    case "control":
      return {
        text: `control ${e.action ?? ""}${e.node_id ? ` ${e.node_id}` : ""}${e.decision ? ` → ${e.decision}` : ""}`,
        tone: TONES.control,
      };
    case "done":
      return { text: "run complete ✓", tone: TONES.stageDone };
    case "failed":
      return { text: `run failed — ${e.error ?? ""}`, tone: TONES.fail };
    case "cancelled":
      return { text: "run cancelled", tone: TONES.warn };
    default:
      return { text: e.type, tone: TONES.console };
  }
}

export function ActivityFeed({
  runId,
  events,
  terminal,
  error,
}: {
  runId: string | null;
  events: StampedRunEvent[];
  terminal: RunTerminal;
  error: string | null;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-collapse to a slim status bar while no run is active.
  useEffect(() => {
    if (runId === null) setCollapsed(true);
    else setCollapsed(false);
  }, [runId]);

  useEffect(() => {
    if (!collapsed && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, collapsed]);

  const terminalBadge =
    terminal === "succeeded"
      ? { label: "complete", tone: "bg-up-600/15 text-up-500" }
      : terminal === "failed"
        ? { label: "failed", tone: "bg-down-600/15 text-down-500" }
        : terminal === "cancelled"
          ? { label: "cancelled", tone: "bg-amber-500/10 text-amber-300" }
          : terminal === "running"
            ? { label: "running", tone: "bg-accent-600/15 text-accent-400" }
            : null;

  // Per-symbol ticker events render in the phase's LiveRunStatus panel, not
  // here — keep the scrollback to stage/node/console/control/terminal events.
  const visibleEvents = events.filter(
    ({ event }) => event.type !== "ticker_begin" && event.type !== "ticker" && event.type !== "ticker_end",
  );

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        disabled={!runId}
        className="flex w-9 shrink-0 flex-col items-center justify-between border-l border-ink-800 bg-ink-900/50 py-3 text-slate-600 transition-colors hover:text-slate-400"
        title={runId ? "Expand activity feed" : "No active run"}
      >
        <span className="text-2xs uppercase tracking-widest [writing-mode:vertical-rl]">activity</span>
        {runId && terminal === "running" ? (
          <span className="h-2 w-2 animate-pulse rounded-full bg-accent-500" />
        ) : (
          <span className="h-2 w-2 rounded-full bg-ink-700" />
        )}
      </button>
    );
  }

  return (
    <aside className="flex w-[340px] shrink-0 flex-col border-l border-ink-800 bg-ink-900/40">
      <div className="flex items-center justify-between border-b border-ink-800/60 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-2xs font-semibold uppercase tracking-widest text-slate-500">Activity</span>
          {terminalBadge && (
            <span className={`rounded px-1.5 py-0.5 text-2xs font-medium ${terminalBadge.tone}`}>
              {terminalBadge.label}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="rounded px-1 text-xs text-slate-600 hover:text-slate-300"
          title="Collapse"
        >
          ›
        </button>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed">
        {!runId && (
          <p className="text-slate-600">
            Start a scan or AI search run — every event streams here live.
          </p>
        )}
        {runId && events.length === 0 && (
          <p className="text-slate-600">Connecting to run stream…</p>
        )}
        {visibleEvents.map(({ at, event }, i) => {
          const line = feedLine(event);
          return (
            <div key={i} className="flex gap-2">
              <span className="shrink-0 text-slate-700">{at}</span>
              <span className={`min-w-0 break-words ${line.tone}`}>{line.text}</span>
            </div>
          );
        })}
        {runId && terminal === "failed" && error && (
          <div className="text-down-500">failed — {error}</div>
        )}
      </div>
    </aside>
  );
}
