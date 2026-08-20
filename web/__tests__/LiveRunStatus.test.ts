import { describe, expect, it } from "vitest";
import { deriveRunningNode, deriveTicker } from "@/components/flow/LiveRunStatus";
import type { StampedRunEvent } from "@/lib/runEvents";
import type { RunEvent } from "@/lib/types";

function ev(type: RunEvent["type"], extra: Omit<RunEvent, "type"> = {}): StampedRunEvent {
  return { at: "12:00:00", event: { type, ...extra } };
}

describe("deriveTicker", () => {
  it("returns null with no ticker events", () => {
    expect(deriveTicker([])).toBeNull();
    expect(deriveTicker([ev("stage", { text: "x" })])).toBeNull();
  });

  it("tracks the current span across throttled ticker events", () => {
    const events = [
      ev("ticker_begin", { description: "Batch OHLCV", total: 10 }),
      ev("ticker", { index: 1, symbol: "AAPL" }),
      ev("ticker", { index: 6, symbol: "MSFT" }),
    ];
    expect(deriveTicker(events)).toEqual({
      description: "Batch OHLCV",
      total: 10,
      index: 6,
      symbol: "MSFT",
      done: false,
    });
  });

  it("marks a span done on ticker_end", () => {
    const events = [
      ev("ticker_begin", { description: "Scoring", total: 5 }),
      ev("ticker", { index: 5, symbol: "NVDA" }),
      ev("ticker_end"),
    ];
    const state = deriveTicker(events);
    expect(state).not.toBeNull();
    expect(state?.done).toBe(true);
    expect(state?.index).toBe(5);
  });

  it("resets on the next ticker_begin", () => {
    const events = [
      ev("ticker_begin", { description: "Batch OHLCV", total: 10 }),
      ev("ticker", { index: 10, symbol: "NVDA" }),
      ev("ticker_end"),
      ev("ticker_begin", { description: "Scoring", total: 5 }),
    ];
    expect(deriveTicker(events)).toMatchObject({
      description: "Scoring",
      total: 5,
      index: 0,
      symbol: null,
      done: false,
    });
  });
});

describe("deriveRunningNode", () => {
  it("tracks the node currently running and clears it on completion", () => {
    const running = ev("node", { node_id: "sc_1", tool_id: "scanner", status: "running" });
    const done = ev("node", { node_id: "sc_1", tool_id: "scanner", status: "ok", kept: 3 });
    expect(deriveRunningNode([running])).toBe("sc_1");
    expect(deriveRunningNode([running, done])).toBeNull();
    expect(deriveRunningNode([running, done, ev("node", { node_id: "sr_1", tool_id: "search", status: "running" })])).toBe(
      "sr_1",
    );
  });
});
