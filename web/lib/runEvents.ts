import { useEffect, useState } from "react";
import { subscribeToRunEvents } from "./api";
import type { RunEvent } from "./types";

export type RunTerminal = "idle" | "running" | "succeeded" | "failed" | "cancelled";

export interface StampedRunEvent {
  at: string;
  event: RunEvent;
}

export interface RunEvents {
  events: StampedRunEvent[];
  terminal: RunTerminal;
  error: string | null;
}

/**
 * Subscribe to a run's SSE stream and surface the raw events plus the
 * terminal state. Replays a terminal event when the run already finished.
 */
export function useRunEvents(runId: string | null): RunEvents {
  const [events, setEvents] = useState<StampedRunEvent[]>([]);
  const [terminal, setTerminal] = useState<RunTerminal>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEvents([]);
    setTerminal("idle");
    setError(null);
    if (!runId) return;
    const unsub = subscribeToRunEvents(runId, (e) => {
      const stamped = { at: new Date().toLocaleTimeString("en-US", { hour12: false }), event: e };
      setEvents((prev) => [...prev.slice(-300), stamped]);
      if (e.type === "done") {
        setTerminal("succeeded");
      } else if (e.type === "failed") {
        setTerminal("failed");
        setError(e.error ?? null);
      } else if (e.type === "cancelled") {
        setTerminal("cancelled");
      } else {
        setTerminal("running");
      }
    });
    return unsub;
  }, [runId]);

  return { events, terminal, error };
}
