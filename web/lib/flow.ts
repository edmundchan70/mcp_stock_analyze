import type { GraphDefinition, RunSummary } from "./types";
import { fmtCompact, fmtPct, fmtRatio, fmtUsd } from "./format";

export type Family = "ep" | "vcp" | "bo" | "zhao" | "premarket";
export type UniverseSource = "paste" | "snapshot";
export type PhaseId = 1 | 2 | 3 | 4 | 5;

export interface FlowState {
  phase: PhaseId;
  runName: string;
  family: Family;
  universeSource: UniverseSource;
  universeText: string;
  scannerVars: Record<string, string | number | boolean>;
  scanRunId: string | null;
  scanRows: Record<string, unknown>[];
  searchRunId: string | null;
  reportRows: Record<string, unknown>[];
}

export type FlowAction =
  | { type: "reset" }
  | { type: "hydrate"; state: FlowState }
  | { type: "setPhase"; phase: PhaseId }
  | { type: "setRunName"; name: string }
  | { type: "setFamily"; family: Family }
  | { type: "setUniverseSource"; source: UniverseSource }
  | { type: "setUniverseText"; text: string }
  | { type: "setScannerVar"; key: string; value: string | number | boolean }
  | { type: "setScannerVars"; vars: Record<string, string | number | boolean> }
  | { type: "setScanRun"; id: string | null }
  | { type: "setScanRows"; rows: Record<string, unknown>[] }
  | { type: "setSearchRun"; id: string | null }
  | { type: "setReportRows"; rows: Record<string, unknown>[] };

export const FLOW_STORAGE_KEY = "stock-scan-flow-v1";

export const FAMILY_LABELS: Record<Family, string> = {
  ep: "Episodic Pivot",
  vcp: "VCP",
  bo: "Breakout",
  zhao: "照妖鏡",
  premarket: "Premarket",
};

export const FAMILY_PIPELINES: Record<Family, string> = {
  ep: "daily_ep_scan",
  vcp: "daily_vcp_scan",
  bo: "daily_bo_scan",
  zhao: "daily_zhao_scan",
  premarket: "daily_premarket_scan",
};

/**
 * Families that run AI Search (phase 4) before the report.
 * zhao + premarket skip it (rate limits): stepper becomes 1→2→3→5 and the
 * report phase renders the scanner bucket directly.
 */
export const FAMILY_HAS_SEARCH: Record<Family, boolean> = {
  ep: true,
  vcp: true,
  bo: true,
  zhao: false,
  premarket: false,
};

/** Phases shown in the stepper for a family (skips AI Search when absent). */
export function phasesForFamily(family: Family): PhaseId[] {
  return FAMILY_HAS_SEARCH[family] ? [1, 2, 3, 4, 5] : [1, 2, 3, 5];
}

export const PHASES: { id: PhaseId; label: string; caption: string }[] = [
  { id: 1, label: "Universe", caption: "Define the symbol set" },
  { id: 2, label: "Scanner", caption: "Filters + results" },
  { id: 3, label: "Pattern", caption: "Chart evidence" },
  { id: 4, label: "AI Search", caption: "Enrich survivors" },
  { id: 5, label: "Report", caption: "Ranked output" },
];

export function initialFlowState(): FlowState {
  return {
    phase: 1,
    runName: "scan",
    family: "bo",
    universeSource: "paste",
    universeText: "",
    scannerVars: {},
    scanRunId: null,
    scanRows: [],
    searchRunId: null,
    reportRows: [],
  };
}

export function flowReducer(state: FlowState, action: FlowAction): FlowState {
  switch (action.type) {
    case "reset":
      return initialFlowState();
    case "hydrate":
      return { ...initialFlowState(), ...action.state };
    case "setPhase":
      return { ...state, phase: action.phase };
    case "setRunName":
      return { ...state, runName: action.name };
    case "setFamily":
      // Premarket universe default = market sweep (research 03); a pasted
      // watchlist keeps paste mode.
      if (action.family === "premarket" && !String(state.universeText ?? "").trim()) {
        return { ...state, family: action.family, universeSource: "snapshot" };
      }
      return { ...state, family: action.family };
    case "setUniverseSource":
      return { ...state, universeSource: action.source };
    case "setUniverseText":
      return { ...state, universeText: action.text };
    case "setScannerVar":
      return {
        ...state,
        scannerVars: { ...state.scannerVars, [action.key]: action.value },
      };
    case "setScannerVars":
      return { ...state, scannerVars: action.vars };
    case "setScanRun":
      return { ...state, scanRunId: action.id };
    case "setScanRows":
      return { ...state, scanRows: action.rows };
    case "setSearchRun":
      return { ...state, searchRunId: action.id };
    case "setReportRows":
      return { ...state, reportRows: action.rows };
  }
}

// ── localStorage persistence (reload recovery) ──────────────────────

export function loadFlowDraft(): FlowState {
  if (typeof window === "undefined") return initialFlowState();
  try {
    const raw = window.localStorage.getItem(FLOW_STORAGE_KEY);
    if (!raw) return initialFlowState();
    const parsed = JSON.parse(raw) as Partial<FlowState>;
    return { ...initialFlowState(), ...parsed };
  } catch {
    return initialFlowState();
  }
}

export function saveFlowDraft(state: FlowState): void {
  try {
    window.localStorage.setItem(FLOW_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // storage unavailable (private mode) — ignore
  }
}

export function clearFlowDraft(): void {
  try {
    window.localStorage.removeItem(FLOW_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// ── universe helpers ────────────────────────────────────────────────

/** Client-side preview parse: uppercase 1–5 char ticker tokens. */
export function parseSymbolText(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(/[\s,;]+/)) {
    const sym = raw.trim().toUpperCase();
    if (/^[A-Z]{1,5}$/.test(sym) && !seen.has(sym)) {
      seen.add(sym);
      out.push(sym);
    }
  }
  return out;
}

export function universeSymbolCount(state: FlowState): number {
  if (state.universeSource === "snapshot") return -1; // unknown until preview
  return parseSymbolText(state.universeText).length;
}

// ── graph builders (walked by the existing backend, unchanged) ─────

export function buildScannerGraph(
  family: Family,
  scannerVars: Record<string, string | number | boolean>,
): GraphDefinition {
  return {
    name: `${FAMILY_LABELS[family]} Scanner`,
    nodes: [
      { id: "universe", type: "universe", position: { x: 0, y: 0 }, variables: {} },
      {
        id: "sc_1",
        type: "scanner",
        position: { x: 0, y: 0 },
        variables: { family, ...scannerVars },
      },
    ],
    edges: [
      { id: "e1", source: "universe", sourceHandle: "out", target: "sc_1", targetHandle: "universe" },
    ],
  };
}

export function buildSearchGraph(
  family: Family,
  scannerVars: Record<string, string | number | boolean>,
): GraphDefinition {
  return {
    name: `${FAMILY_LABELS[family]} Full Scan`,
    nodes: [
      { id: "universe", type: "universe", position: { x: 0, y: 0 }, variables: {} },
      {
        id: "sc_1",
        type: "scanner",
        position: { x: 0, y: 0 },
        variables: { family, ...scannerVars },
      },
      { id: "sr_1", type: "search", position: { x: 0, y: 0 }, variables: {} },
      { id: "r_1", type: "report", position: { x: 0, y: 0 }, variables: {} },
    ],
    edges: [
      { id: "e1", source: "universe", sourceHandle: "out", target: "sc_1", targetHandle: "universe" },
      { id: "e2", source: "sc_1", sourceHandle: "bucket", target: "sr_1", targetHandle: "in" },
      { id: "e3", source: "sr_1", sourceHandle: "out", target: "r_1", targetHandle: "structural" },
    ],
  };
}

export function scanRunBody(state: FlowState): Record<string, unknown> {
  return {
    name: state.runName,
    pipeline_type: FAMILY_PIPELINES[state.family],
    graph: buildScannerGraph(state.family, state.scannerVars),
    universe_source: state.universeSource,
    force_symbols: state.universeSource === "snapshot" ? "" : state.universeText,
  };
}

export function searchRunBody(state: FlowState): Record<string, unknown> {
  const survivors = state.scanRows.map((r) => String(r.symbol).toUpperCase()).join(", ");
  return {
    name: `${state.runName} · AI Search`,
    pipeline_type: FAMILY_PIPELINES[state.family],
    graph: buildSearchGraph(state.family, state.scannerVars),
    universe_source: "paste",
    force_symbols: survivors,
  };
}

// ── phase gating ────────────────────────────────────────────────────

/** Whether a phase cannot be entered yet (no universe / no rows / no report). */
export function phaseLocked(state: FlowState, phase: PhaseId): boolean {
  switch (phase) {
    case 1:
      return false;
    case 2:
      return universeSymbolCount(state) === 0;
    case 3:
    case 4:
      return state.scanRows.length === 0;
    case 5:
      return state.reportRows.length === 0;
  }
}

/** Whether a phase's work is complete (used for stepper check marks). */
export function phaseDone(state: FlowState, phase: PhaseId): boolean {
  switch (phase) {
    case 1:
      return universeSymbolCount(state) > 0;
    case 2:
      return state.scanRows.length > 0;
    case 3:
      return state.scanRows.length > 0; // review-only phase
    case 4:
      return state.reportRows.length > 0;
    case 5:
      return state.reportRows.length > 0;
  }
}

/** Numeric rating extracted from a scanner/report row (any shape). */
export function rowRating(row: Record<string, unknown>): number {
  for (const k of ["rating", "ep_rating", "final_rating", "funnel_stars", "structural_rating", "setup_rating", "strength"]) {
    const v = row[k];
    if (typeof v === "number" && !Number.isNaN(v)) return v;
    const n = Number(v);
    if (v !== null && v !== undefined && v !== "" && !Number.isNaN(n)) return n;
  }
  return 0;
}

/** Active run id for the current phase (feed subscription target). */
export function activeRunId(state: FlowState): string | null {
  if (state.phase === 4) return state.searchRunId;
  if (state.phase === 2) return state.scanRunId;
  return null;
}

/** Settled run status for a run summary. */
export function isRunRunning(run: RunSummary | null): boolean {
  return run !== null && (run.status === "queued" || run.status === "running");
}

// ── artifact extraction (run → phase data) ─────────────────────────

export function scannerRowsFromArtifacts(artifacts: Record<string, unknown>): Record<string, unknown>[] {
  const node = artifacts["node:sc_1"] as { output_rows?: Record<string, unknown[]> } | undefined;
  const rows = (node?.output_rows?.bucket ?? []) as unknown;
  return Array.isArray(rows) ? (rows as Record<string, unknown>[]) : [];
}

export function reportRowsFromArtifacts(artifacts: Record<string, unknown>): Record<string, unknown>[] {
  const node = artifacts["node:r_1"] as { output_rows?: Record<string, unknown[]> } | undefined;
  const rows = (node?.output_rows?.rated ?? []) as unknown;
  if (Array.isArray(rows) && rows.length > 0) return rows as Record<string, unknown>[];
  const mt = artifacts["merge_table"] as { rows?: Record<string, unknown>[] } | undefined;
  return Array.isArray(mt?.rows) ? mt.rows : [];
}

// ── plain-language detection explanations ──────────────────────────

/** Which detection checks passed/failed for a scanner row (per family). */
export function rowExplanation(family: Family, row: Record<string, unknown>): string[] {
  if (family === "ep") {
    const parts: string[] = [];
    parts.push(`gap ${fmtPct(row.gap_pct)} · RVOL10 ${fmtRatio(row.rvol10)} · price ${fmtUsd(row.price)}`);
    parts.push(`event-day $vol ${fmtUsd(row.event_dollar_volume)} · 50d ADV$ ${fmtUsd(row.avg_dollar_volume_50d)}`);
    if (row.market_cap !== null && row.market_cap !== undefined) {
      parts.push(`market cap ${fmtUsd(row.market_cap)}`);
    }
    return parts;
  }
  if (family === "bo") {
    const essentials: [string, string][] = [
      ["prior_impulse", "prior impulse ≥30%"],
      ["adr20", "ADR envelope 4–12%"],
      ["base_duration", "base 5–40d"],
      ["vci", "VCI ≤0.65"],
      ["ma_stack", "MA stack + surfing"],
      ["pivot_kde", "KDE pivot found"],
      ["higher_lows", "higher lows"],
      ["dryup", "volume dry-up"],
      ["volume_surge", "volume surge ≥1.5×"],
    ];
    const lines = essentials.map(([k, label]) =>
      row[k] === true ? `✓ ${label}` : row[k] === false ? `✗ ${label}` : `· ${label}`,
    );
    lines.unshift(
      `variant ${String(row.variant ?? "—")} · impulse ${fmtPct(row.prior_impulse_pct)} · surge ${fmtRatio(row.surge_pct)} · base ${fmtCompact(row.base_duration_days, { digits: 0 })}d`,
    );
    return lines;
  }
  if (family === "vcp") {
    return [
      `structural ${row.structural_rating ?? "—"}★ · RS ${fmtCompact(row.rs_rating, { digits: 1 })}`,
      `contractions ${fmtCompact(row.contraction_count, { digits: 0 })} · 52w proximity ${fmtPct(row.proximity_52w_pct)} below`,
      `trough ${row.trough_symmetry_score ?? "—"} · peak ${row.peak_symmetry_score ?? "—"} · range ${row.dollar_range_score ?? "—"} · depth ${row.depth_score ?? "—"}`,
      `tight closes ${row.tight_closes_score ?? "—"} · volume decay ${row.volume_decay_score ?? "—"} · time ${row.time_contraction_score ?? "—"}`,
    ];
  }
  if (family === "zhao") {
    const variant = String(row.variant ?? "realtime");
    const lines = [
      `${variant} · strength ${row.strength ?? "—"}★ · close ${fmtUsd(row.close)} · SMA20 ${fmtUsd(row.sma20)}`,
      `today ${fmtPct(row.today_pct)} · bench ${fmtPct(row.bench_pct)} (${row.bench_symbol ?? "SPY"}) · margin ${fmtPct(row.margin_pct)}`,
    ];
    if (variant === "daily") {
      lines.push(`20d RS ${fmtPct(row.rs_20d)} · 52w ${fmtPct(row.pct_from_high)} below high · streak ${row.streak ?? "—"}`);
    }
    return lines;
  }
  if (family === "premarket") {
    return [
      `strength ${row.strength ?? "—"}★ · premarket ${fmtPct(row.change_pct)} vs prior close`,
      `${row.vol_flag ? "✓" : "·"} volume × ADV ${fmtRatio(row.adv_20d ?? 0)} · price ${fmtUsd(row.price)}`,
      `sector ${row.sector ?? "Unknown"}`,
    ];
  }
  return [];
}

/** Chart overlay anchors derived from a scanner row (BO / VCP / EP). */
export interface PatternOverlay {
  priceLines: { price: number; title: string; color: string }[];
  markers: { time: string; position: "aboveBar" | "belowBar"; color: string; shape: "arrowUp" | "arrowDown" | "circle"; text: string }[];
}

const UP = "#2fbf9a";
const DOWN = "#e05c5c";
const AMBER = "#e0a33c";

export function patternOverlay(family: Family, row: Record<string, unknown>, bars: { datetime: string }[]): PatternOverlay {
  const priceLines: PatternOverlay["priceLines"] = [];
  const markers: PatternOverlay["markers"] = [];
  const lastTime = bars.length > 0 ? toChartTime(bars[bars.length - 1].datetime) : "";

  if (family === "bo") {
    const pivot = Number(row.pivot);
    if (pivot > 0) priceLines.push({ price: pivot, title: "pivot", color: AMBER });
    const hi = Number(row.base_high);
    const lo = Number(row.base_low);
    if (hi > 0) priceLines.push({ price: hi, title: "base high", color: UP });
    if (lo > 0) priceLines.push({ price: lo, title: "base low", color: DOWN });
    const bi = Number(row.breakout_idx);
    if (Number.isFinite(bi) && bi >= 0 && bi < bars.length) {
      markers.push({
        time: toChartTime(bars[bi].datetime),
        position: "belowBar",
        color: UP,
        shape: "arrowUp",
        text: "breakout",
      });
    }
  } else if (family === "vcp") {
    const contractions = Array.isArray(row.contractions) ? (row.contractions as Record<string, unknown>[]) : [];
    contractions.forEach((c, i) => {
      const hp = Number(c.high_pivot);
      const lp = Number(c.low_pivot);
      if (hp > 0) priceLines.push({ price: hp, title: `C${i + 1} high`, color: UP });
      if (lp > 0) priceLines.push({ price: lp, title: `C${i + 1} low`, color: DOWN });
    });
  } else if (family === "ep") {
    // Event (gap) day is the last bar — mark it and the prior close.
    if (lastTime) {
      markers.push({
        time: lastTime,
        position: "belowBar",
        color: AMBER,
        shape: "circle",
        text: "gap day",
      });
    }
    const prior = Number(row.prior_close);
    if (prior > 0) priceLines.push({ price: prior, title: "prior close", color: DOWN });
  } else if (family === "zhao") {
    const sma = Number(row.sma20);
    if (sma > 0) priceLines.push({ price: sma, title: "SMA20", color: AMBER });
  }
  return { priceLines, markers };
}

/** Convert an ISO datetime (or date string) to a YYYY-MM-DD business day. */
export function toChartTime(datetime: string): string {
  return datetime.slice(0, 10);
}
