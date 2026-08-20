import { beforeEach, describe, expect, it } from "vitest";
import {
  buildScannerGraph,
  buildSearchGraph,
  FAMILY_HAS_SEARCH,
  FAMILY_PIPELINES,
  flowReducer,
  initialFlowState,
  parseSymbolText,
  patternOverlay,
  phaseDone,
  phaseLocked,
  phasesForFamily,
  reportRowsFromArtifacts,
  rowExplanation,
  rowRating,
  scannerRowsFromArtifacts,
  scanRunBody,
  searchRunBody,
  streakLabel,
  type FlowState,
} from "@/lib/flow";

function draft(overrides: Partial<FlowState> = {}): FlowState {
  return { ...initialFlowState(), ...overrides };
}

describe("flow reducer", () => {
  it("starts at Universe with sensible defaults", () => {
    const s = initialFlowState();
    expect(s.phase).toBe(1);
    expect(s.family).toBe("bo");
    expect(s.universeSource).toBe("paste");
    expect(s.universeText).toBe("");
    expect(s.scanRows).toEqual([]);
  });

  it("setUniverseText updates the text", () => {
    const s = flowReducer(initialFlowState(), { type: "setUniverseText", text: "AAPL MSFT" });
    expect(s.universeText).toBe("AAPL MSFT");
  });

  it("setScannerVar merges into scannerVars", () => {
    const s = flowReducer(initialFlowState(), { type: "setScannerVar", key: "min_price", value: 5 });
    expect(s.scannerVars).toEqual({ min_price: 5 });
  });

  it("setScanRows populates survivors", () => {
    const rows = [{ symbol: "AAPL" }];
    const s = flowReducer(initialFlowState(), { type: "setScanRows", rows });
    expect(s.scanRows).toBe(rows);
  });

  it("reset returns to initial state", () => {
    const s = flowReducer(draft({ phase: 4, scanRows: [{ symbol: "AAPL" }] }), { type: "reset" });
    expect(s.phase).toBe(1);
    expect(s.scanRows).toEqual([]);
  });

  it("hydrate merges a persisted draft over defaults", () => {
    const s = flowReducer(initialFlowState(), {
      type: "hydrate",
      state: { ...initialFlowState(), phase: 3, universeText: "NVDA" },
    });
    expect(s.phase).toBe(3);
    expect(s.universeText).toBe("NVDA");
    expect(s.family).toBe("bo");
  });
});

describe("universe parsing", () => {
  it("uppercases, dedupes, and skips junk", () => {
    expect(parseSymbolText("aapl, msft\nnvda  TSLA;msft 12345 !!!")).toEqual(["AAPL", "MSFT", "NVDA", "TSLA"]);
  });

  it("returns empty for blank input", () => {
    expect(parseSymbolText("   \n")).toEqual([]);
  });
});

describe("phase gating", () => {
  const withRows = draft({ universeText: "AAPL", scanRows: [{ symbol: "AAPL" }], reportRows: [{ symbol: "AAPL" }] });

  it("locks the scanner until a universe exists", () => {
    expect(phaseLocked(draft(), 2)).toBe(true);
    expect(phaseLocked(draft({ universeText: "AAPL" }), 2)).toBe(false);
  });

  it("locks pattern + search until survivors exist", () => {
    expect(phaseLocked(draft({ universeText: "AAPL" }), 3)).toBe(true);
    expect(phaseLocked(draft({ universeText: "AAPL", scanRows: [{ symbol: "AAPL" }] }), 3)).toBe(false);
    expect(phaseLocked(withRows, 4)).toBe(false);
  });

  it("locks the report until rows are ranked", () => {
    expect(phaseLocked(draft({ universeText: "AAPL", scanRows: [{ symbol: "AAPL" }] }), 5)).toBe(true);
    expect(phaseLocked(withRows, 5)).toBe(false);
  });

  it("phaseDone reflects scan/report completion", () => {
    expect(phaseDone(draft(), 1)).toBe(false);
    expect(phaseDone(withRows, 2)).toBe(true);
    expect(phaseDone(withRows, 3)).toBe(true);
    expect(phaseDone(withRows, 4)).toBe(true);
    expect(phaseDone(withRows, 5)).toBe(true);
    expect(phaseDone(draft({ universeText: "AAPL", scanRows: [{ symbol: "AAPL" }] }), 5)).toBe(false);
  });
});

describe("artifact extraction", () => {
  it("pulls the scanner bucket from the node artifact", () => {
    const artifacts = { "node:sc_1": { output_rows: { bucket: [{ symbol: "AAPL" }, { symbol: "NVDA" }] } } };
    expect(scannerRowsFromArtifacts(artifacts)).toEqual([{ symbol: "AAPL" }, { symbol: "NVDA" }]);
  });

  it("falls back to merge_table for report rows", () => {
    expect(reportRowsFromArtifacts({})).toEqual([]);
    expect(reportRowsFromArtifacts({ merge_table: { rows: [{ symbol: "MSFT" }] } })).toEqual([
      { symbol: "MSFT" },
    ]);
    expect(
      reportRowsFromArtifacts({ "node:r_1": { output_rows: { rated: [{ symbol: "TSLA" }] } } }),
    ).toEqual([{ symbol: "TSLA" }]);
  });
});

describe("row rating + explanation", () => {
  it("reads the rating from any supported key", () => {
    expect(rowRating({ rating: 4.5 })).toBe(4.5);
    expect(rowRating({ ep_rating: "5" })).toBe(5);
    expect(rowRating({})).toBe(0);
  });

  it("lists pass/fail checks for BO rows", () => {
    const lines = rowExplanation("bo", {
      variant: "moderate-lose",
      prior_impulse_pct: 45.2,
      surge_pct: 2.1,
      base_duration_days: 12,
      prior_impulse: true,
      adr20: true,
      base_duration: false,
    });
    expect(lines[0]).toContain("variant moderate-lose");
    expect(lines).toContain("✓ prior impulse ≥30%");
    expect(lines).toContain("✓ ADR envelope 4–12%");
    expect(lines).toContain("✗ base 5–40d");
  });

  it("renders EP price/liquidity lines", () => {
    const lines = rowExplanation("ep", {
      gap_pct: 4.2,
      rvol10: 3.5,
      price: 12.34,
      event_dollar_volume: 5_000_000,
      avg_dollar_volume_50d: 2_500_000,
    });
    expect(lines[0]).toContain("gap 4.2%");
    expect(lines[1]).toContain("event-day $vol $5.0M");
  });
});

describe("pattern overlays", () => {
  const bars = [
    { datetime: "2026-08-10" },
    { datetime: "2026-08-11" },
    { datetime: "2026-08-12" },
  ];

  it("anchors BO base high/low, pivot, and breakout marker", () => {
    const overlay = patternOverlay(
      "bo",
      { base_high: 30, base_low: 20, pivot: 25, breakout_idx: 2 },
      bars,
    );
    expect(overlay.priceLines.map((p) => p.title)).toEqual(["pivot", "base high", "base low"]);
    expect(overlay.markers).toEqual([
      { time: "2026-08-12", position: "belowBar", color: "#2fbf9a", shape: "arrowUp", text: "breakout" },
    ]);
  });

  it("marks the last bar as the gap day for EP", () => {
    const overlay = patternOverlay("ep", { prior_close: 40 }, bars);
    expect(overlay.markers[0].text).toBe("gap day");
    expect(overlay.markers[0].time).toBe("2026-08-12");
    expect(overlay.priceLines[0].title).toBe("prior close");
  });

  it("ignores a breakout index outside the bar range", () => {
    const overlay = patternOverlay("bo", { base_high: 30, pivot: 25, breakout_idx: 99 }, bars);
    expect(overlay.markers).toEqual([]);
  });
});

describe("run bodies", () => {
  it("scanRunBody posts the scanner graph with pasted symbols", () => {
    const body = scanRunBody(draft({ runName: "nightly", universeText: "AAPL, MSFT", family: "vcp" }));
    expect(body.name).toBe("nightly");
    expect(body.pipeline_type).toBe("daily_vcp_scan");
    expect(body.universe_source).toBe("paste");
    expect(body.force_symbols).toBe("AAPL, MSFT");
    const graph = buildScannerGraph("vcp", {});
    expect(body.graph).toEqual(graph);
    expect(graph.nodes.map((n) => n.type)).toEqual(["universe", "scanner"]);
  });

  it("searchRunBody posts the full graph with survivors as the paste universe", () => {
    const body = searchRunBody(
      draft({ scanRows: [{ symbol: "aapl" }, { symbol: "NVDA" }], family: "bo" }),
    );
    expect(body.pipeline_type).toBe("daily_bo_scan");
    expect(body.force_symbols).toBe("AAPL, NVDA");
    const graph = buildSearchGraph("bo", {});
    expect(body.graph).toEqual(graph);
    expect(graph.nodes.map((n) => n.type)).toEqual(["universe", "scanner", "search", "report"]);
    expect(graph.edges.length).toBe(3);
  });
});

// ── zhao + premarket families ──────────────────────────────────────

describe("zhao + premarket families", () => {
  it("registers labels + pipelines", () => {
    expect(FAMILY_PIPELINES.zhao).toBe("daily_zhao_scan");
    expect(FAMILY_PIPELINES.premarket).toBe("daily_premarket_scan");
  });

  it("skips AI Search (phase 4) in the stepper", () => {
    expect(FAMILY_HAS_SEARCH.zhao).toBe(false);
    expect(FAMILY_HAS_SEARCH.premarket).toBe(false);
    expect(FAMILY_HAS_SEARCH.bo).toBe(true);
    expect(phasesForFamily("zhao")).toEqual([1, 2, 3, 5]);
    expect(phasesForFamily("premarket")).toEqual([1, 2, 3, 5]);
    expect(phasesForFamily("ep")).toEqual([1, 2, 3, 4, 5]);
  });

  it("defaults premarket to the market sweep when no symbols pasted", () => {
    expect(flowReducer(initialFlowState(), { type: "setFamily", family: "premarket" }).universeSource).toBe(
      "snapshot",
    );
    // A pasted watchlist keeps paste mode.
    const withText = flowReducer(draft({ universeText: "AAPL" }), { type: "setFamily", family: "premarket" });
    expect(withText.universeSource).toBe("paste");
    expect(flowReducer(initialFlowState(), { type: "setFamily", family: "zhao" }).universeSource).toBe("paste");
  });

  it("reads strength as the rating key", () => {
    expect(rowRating({ strength: 4 })).toBe(4);
    expect(rowRating({ strength: "5" })).toBe(5);
  });

  it("builds the zhao scanner graph with variant vars", () => {
    const graph = buildScannerGraph("zhao", { zhao_variant: "daily", zhao_benchmark: "QQQ" });
    const scanner = graph.nodes.find((n) => n.type === "scanner");
    expect(scanner?.variables).toMatchObject({ family: "zhao", zhao_variant: "daily", zhao_benchmark: "QQQ" });
  });

  it("explains zhao realtime rows", () => {
    const lines = rowExplanation("zhao", {
      variant: "realtime",
      strength: 4,
      close: 100,
      sma20: 95,
      today_pct: 2.5,
      bench_pct: 0.5,
      bench_symbol: "SPY",
      margin_pct: 2.0,
    });
    expect(lines[0]).toContain("realtime");
    expect(lines[0]).toContain("strength 4★");
    expect(lines[1]).toContain("bench 0.5% (SPY)");
    expect(lines[1]).toContain("margin 2%");
  });

  it("explains zhao daily rows with RS + streak", () => {
    const lines = rowExplanation("zhao", {
      variant: "daily",
      strength: 5,
      close: 100,
      sma20: 95,
      today_pct: 1.0,
      bench_pct: 0.2,
      margin_pct: 0.8,
      rs_20d: 12.5,
      pct_from_high: -3.0,
      streak: 3,
    });
    expect(lines[2]).toContain("20d RS 12.5%");
    expect(lines[2]).toContain("52w -3%");
    expect(lines[2]).toContain("streak 3+");
  });

  it("labels streaks as 1 / 2 / 3+", () => {
    expect(streakLabel(0)).toBe("—");
    expect(streakLabel(1)).toBe("1");
    expect(streakLabel(2)).toBe("2");
    expect(streakLabel(3)).toBe("3+");
    expect(streakLabel(10)).toBe("3+");
  });

  it("explains premarket rows with change % + volume flag", () => {
    const lines = rowExplanation("premarket", {
      strength: 3,
      change_pct: 6.2,
      price: 45.5,
      vol_flag: true,
      adv_20d: 1_000_000,
      sector: "Technology",
    });
    expect(lines[0]).toContain("premarket 6.2%");
    expect(lines[0]).toContain("strength 3★");
    expect(lines[1]).toContain("✓ volume × ADV");
    expect(lines[2]).toContain("Technology");
  });

  it("overlays SMA20 + last-bar marker for zhao charts", () => {
    const overlay = patternOverlay("zhao", { sma20: 25.5 }, [{ datetime: "2026-08-12" }]);
    expect(overlay.priceLines).toEqual([{ price: 25.5, title: "SMA20", color: "#e0a33c" }]);
    expect(overlay.markers).toEqual([
      { time: "2026-08-12", position: "belowBar", color: "#e0a33c", shape: "circle", text: "today" },
    ]);
  });
});
