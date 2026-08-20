"use client";

import { useEffect, useMemo, useState } from "react";
import { createRun, getRun, listTools } from "@/lib/api";
import { defaultsFor, scannerGroups, visibleVars } from "@/lib/graph";
import { fmtCompact, fmtPct } from "@/lib/format";
import {
  FAMILY_HAS_SEARCH,
  FAMILY_LABELS,
  parseSymbolText,
  rowExplanation,
  rowRating,
  scanRunBody,
  scannerRowsFromArtifacts,
  streakLabel,
  type Family,
  type FlowAction,
  type FlowState,
} from "@/lib/flow";
import type { RunTerminal, StampedRunEvent } from "@/lib/runEvents";
import type { ToolSpec, VariableDef } from "@/lib/types";
import { LiveRunStatus } from "./LiveRunStatus";
import { PresetManager } from "./PresetManager";
import { ChipRow } from "./filters/Chips";
import { FilterRow } from "./filters/FilterRow";
import { Section } from "./filters/Section";
import { Switch } from "./filters/Switch";

function familyDefaults(spec: ToolSpec, family: Family): Record<string, string | number | boolean> {
  const all = defaultsFor(spec);
  const visible = visibleVars(spec, { ...all, family });
  const out: Record<string, string | number | boolean> = { family };
  for (const v of visible) out[v.key] = all[v.key];
  return out;
}

function initialOpenGroups(family: Family): Record<string, boolean> {
  const groups = scannerGroups(family);
  return { Family: true, ...Object.fromEntries(groups.map((g) => [g, true])) };
}

interface Column {
  key: string;
  label: string;
  numeric?: boolean;
  fmt?: "usd" | "pct" | "ratio" | "num";
}

const COLUMNS: Record<Family, Column[]> = {
  ep: [
    { key: "symbol", label: "Symbol" },
    { key: "gap_pct", label: "Gap %", numeric: true, fmt: "pct" },
    { key: "rvol10", label: "RVOL10", numeric: true, fmt: "ratio" },
    { key: "price", label: "Price", numeric: true, fmt: "usd" },
    { key: "event_dollar_volume", label: "Event $vol", numeric: true, fmt: "usd" },
    { key: "avg_dollar_volume_50d", label: "ADV$ 50d", numeric: true, fmt: "usd" },
    { key: "features_held", label: "Setup", numeric: true },  ],
  bo: [
    { key: "symbol", label: "Symbol" },
    { key: "rating", label: "★", numeric: true },
    { key: "variant", label: "Variant" },
    { key: "prior_impulse_pct", label: "Impulse %", numeric: true, fmt: "pct" },
    { key: "surge_pct", label: "Surge", numeric: true, fmt: "ratio" },
    { key: "base_duration_days", label: "Base d", numeric: true, fmt: "num" },
  ],
  vcp: [
    { key: "symbol", label: "Symbol" },
    { key: "structural_rating", label: "★", numeric: true },
    { key: "rs_rating", label: "RS", numeric: true, fmt: "num" },
    { key: "contraction_count", label: "Contr.", numeric: true, fmt: "num" },
    { key: "proximity_52w_pct", label: "52w prox %", numeric: true, fmt: "pct" },
  ],
  zhao: [
    { key: "symbol", label: "Symbol" },
    { key: "strength", label: "★", numeric: true },
    { key: "variant", label: "Variant" },
    { key: "today_pct", label: "Today %", numeric: true, fmt: "pct" },
    { key: "margin_pct", label: "Margin %", numeric: true, fmt: "pct" },
    { key: "close", label: "Close", numeric: true, fmt: "usd" },
    { key: "sma20", label: "SMA20", numeric: true, fmt: "usd" },
    { key: "pct_from_high", label: "52w %", numeric: true, fmt: "pct" },
    { key: "streak", label: "Streak", numeric: true, fmt: "num" },
    { key: "sector", label: "Sector" },
  ],
  premarket: [
    { key: "symbol", label: "Symbol" },
    { key: "company_name", label: "Name" },
    { key: "change_pct", label: "Change %", numeric: true, fmt: "pct" },
    { key: "price", label: "Price", numeric: true, fmt: "usd" },
    { key: "volume", label: "Vol", numeric: true, fmt: "num" },
    { key: "sector", label: "Sector" },
    { key: "strength", label: "★", numeric: true },
  ],
};

const EP_FEATURES: { key: string; label: string; thresholds: string[] }[] = [
  { key: "base_detected", label: "Base", thresholds: ["ep_base_min_days", "ep_base_max_days"] },
  { key: "volume_spike", label: "Volume spike", thresholds: ["ep_spike_min"] },
  { key: "pullback_contrast", label: "Pullback contrast", thresholds: ["ep_pullback_vol_ratio", "ep_pullback_depth_pct"] },
  { key: "ema_support", label: "EMA 9/20/50", thresholds: ["ep_ema_touch_pct"] },
  { key: "vwap_support", label: "VWAP support", thresholds: ["ep_vwap_touch_pct"] },
];

function varUnit(v: VariableDef): string | undefined {
  if (v.key.includes("pct")) return "%";
  if (v.key.includes("ratio") || v.key.includes("spike_min")) return "×";
  if (v.key.includes("days")) return "d";
  if (v.key.includes("price") || v.key.includes("adv") || v.key.includes("mcap")) return "$";
  return undefined;
}

export function ScannerPhase({
  state,
  dispatch,
  runId,
  runTerminal,
  events,
}: {
  state: FlowState;
  dispatch: (a: FlowAction) => void;
  runId: string | null;
  runTerminal: RunTerminal;
  events: StampedRunEvent[];
}) {
  const [spec, setSpec] = useState<ToolSpec | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDesc, setSortDesc] = useState(true);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => initialOpenGroups(state.family));

  useEffect(() => {
    listTools()
      .then((tools) => {
        const scanner = tools.find((t) => t.id === "scanner");
        if (scanner) {
          setSpec(scanner);
          setOpenGroups(initialOpenGroups(state.family));
          dispatch({ type: "setScannerVars", vars: familyDefaults(scanner, state.family) });
        }
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Extract scan rows once the scan run completes.
  useEffect(() => {
    if (runTerminal === "succeeded" && runId) {
      getRun(runId)
        .then((r) => {
          const rows = scannerRowsFromArtifacts(r.artifacts);
          if (rows.length > 0) {
            dispatch({ type: "setScanRows", rows });
            // No-search families (zhao/premarket): the scanner bucket IS the
            // report — rank it directly so phase 5 is reachable without AI Search.
            if (!FAMILY_HAS_SEARCH[state.family]) {
              dispatch({ type: "setReportRows", rows });
            }
          }
        })
        .catch(() => {});
    }
  }, [runTerminal, runId, dispatch, state.family]);

  const vars = spec ? visibleVars(spec, { ...state.scannerVars, family: state.family }) : [];
  const defaults = useMemo(() => (spec ? defaultsFor(spec) : {}), [spec]);
  const grouped = useMemo(() => {
    const groups: { group: string; fields: VariableDef[] }[] = [];
    for (const v of vars) {
      let g = groups.find((x) => x.group === v.group);
      if (!g) {
        g = { group: v.group, fields: [] };
        groups.push(g);
      }
      g.fields.push(v);
    }
    return groups;
  }, [vars]);

  const columns = COLUMNS[state.family];
  const rows = useMemo(() => {
    const q = query.trim().toUpperCase();
    const filtered = q
      ? state.scanRows.filter(
          (r) => String(r.symbol ?? "").toUpperCase().includes(q) || String(r.name ?? "").toUpperCase().includes(q),
        )
      : state.scanRows;
    if (!sortKey) return filtered;
    const dir = sortDesc ? -1 : 1;
    return [...filtered].sort((a, b) => {
      const av = sortKey === "rating" || sortKey === "structural_rating" ? rowRating(a) : a[sortKey];
      const bv = sortKey === "rating" || sortKey === "structural_rating" ? rowRating(b) : b[sortKey];
      const an = Number(av);
      const bn = Number(bv);
      if (av === null || av === undefined || av === "") return 1;
      if (bv === null || bv === undefined || bv === "") return -1;
      if (!Number.isNaN(an) && !Number.isNaN(bn)) return (an - bn) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [state.scanRows, query, sortKey, sortDesc]);

  const technicalOn = Boolean(state.scannerVars["ep_features_enabled"] ?? defaults["ep_features_enabled"] ?? true);
  const enabledFeatures = EP_FEATURES.filter(
    (f) => technicalOn && Boolean(state.scannerVars[`ep_feature_${f.key}`] ?? defaults[`ep_feature_${f.key}`] ?? true),
  );

  const chips = useMemo(() => {
    const out: { id: string; group: string; label: string }[] = [];
    for (const v of vars) {
      if (v.group === "Family") continue;
      const cur = state.scannerVars[v.key] ?? v.default;
      if (String(cur) === String(v.default)) continue;
      const unit = varUnit(v);
      const value = v.kind === "boolean" ? (Boolean(cur) ? "on" : "off") : fmtCompact(Number(cur), { digits: 1 });
      out.push({ id: v.key, group: v.group, label: `${v.label} ${value}${unit ?? ""}` });
    }
    if (state.family === "ep" && technicalOn) {
      for (const f of enabledFeatures) out.push({ id: `feat-${f.key}`, group: "EP technical", label: `${f.label} ✓` });
    }
    return out;
  }, [vars, state.scannerVars, defaults, technicalOn, enabledFeatures, state.family]);

  function toggleSort(key: string) {
    if (sortKey === key) setSortDesc((d) => !d);
    else {
      setSortKey(key);
      setSortDesc(true);
    }
  }

  function jumpTo(group: string) {
    setOpenGroups((g) => ({ ...g, [group]: true }));
  }

  function selectFamily(f: Family) {
    dispatch({ type: "setFamily", family: f });
    dispatch({ type: "setScanRun", id: null });
    dispatch({ type: "setScanRows", rows: [] });
    dispatch({ type: "setSearchRun", id: null });
    dispatch({ type: "setReportRows", rows: [] });
    if (spec) {
      setOpenGroups(initialOpenGroups(f));
      dispatch({ type: "setScannerVars", vars: familyDefaults(spec, f) });
    }
  }

  function setVar(key: string, value: string | number | boolean) {
    dispatch({ type: "setScannerVar", key, value });
  }

  function resetVar(v: VariableDef) {
    setVar(v.key, v.default);
  }

  async function startScan() {
    setBusy(true);
    setError(null);
    try {
      const run = await createRun(scanRunBody(state));
      dispatch({ type: "setScanRun", id: run.id });
      dispatch({ type: "setScanRows", rows: [] });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const running = runTerminal === "running";
  const universeReady = state.universeSource === "snapshot" || parseSymbolText(state.universeText).length > 0;
  const sortLabel = columns.find((c) => c.key === sortKey)?.label;

  // Zhao realtime: benchmark context banner — informational only, never blocks.
  const zhaoBanner =
    state.family === "zhao" &&
    String(state.scannerVars["zhao_variant"] ?? "realtime") === "realtime" &&
    state.scanRows.length > 0
      ? (() => {
          const first = state.scanRows[0];
          const aboveSma = state.scanRows.filter((r) => Number(r.close ?? 0) > Number(r.sma20 ?? 0)).length;
          return {
            benchSymbol: String(first.bench_symbol ?? "SPY"),
            benchPct: Number(first.bench_pct ?? 0),
            aboveSma,
            total: state.scanRows.length,
          };
        })()
      : null;

  return (
    <div className="grid min-h-0 gap-6 lg:grid-cols-[300px_1fr]">
      {/* Left filter rail */}
      <div className="space-y-3">
        <section className="panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Family</h2>
            <PresetManager
              family={state.family}
              currentVars={state.scannerVars}
              onApply={(f, v) => {
                selectFamily(f);
                dispatch({ type: "setScannerVars", vars: { family: f, ...v } });
              }}
            />
          </div>
          <div className="grid grid-cols-3 gap-1 rounded-md border border-ink-700 bg-ink-800/60 p-1">
            {(["ep", "vcp", "bo", "zhao", "premarket"] as Family[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => selectFamily(f)}
                className={`rounded px-2 py-1.5 text-sm font-medium transition-colors duration-150 ${
                  state.family === f
                    ? "bg-accent-600 text-ink-950"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>
        </section>

        {grouped.map((g) => {
          if (g.group === "Family") return null;
          if (g.group === "EP technical") {
            return (
              <Section
                key={g.group}
                title="EP Technical Test"
                open={openGroups[g.group] ?? false}
                onToggle={(open) => setOpenGroups((prev) => ({ ...prev, [g.group]: open }))}
                headerExtra={
                  <Switch
                    size="sm"
                    checked={technicalOn}
                    onChange={(v) => setVar("ep_features_enabled", v)}
                    label="EP technical test"
                  />
                }
              >
                <FilterRow
                  label="Keep if any feature holds"
                  control={
                    <Switch
                      checked={Boolean(state.scannerVars["ep_keep_if_any"] ?? defaults["ep_keep_if_any"] ?? true)}
                      onChange={(v) => setVar("ep_keep_if_any", v)}
                    />
                  }
                />
                <div className="mt-4 space-y-3">
                  {EP_FEATURES.map((f) => {
                    const varDef = g.fields.find((v) => v.key === `ep_feature_${f.key}`);
                    const on = Boolean(state.scannerVars[`ep_feature_${f.key}`] ?? defaults[`ep_feature_${f.key}`] ?? true);
                    return (
                      <div key={f.key}>
                        <FilterRow
                          label={f.label}
                          control={
                            <Switch
                              checked={on}
                              disabled={!technicalOn}
                              onChange={(v) => setVar(`ep_feature_${f.key}`, v)}
                            />
                          }
                        />
                        {technicalOn && on && (
                          <div className="mt-2 space-y-3 rounded-md border border-ink-800/70 bg-ink-900/50 p-3">
                            {f.thresholds.map((tk) => {
                              const tv = g.fields.find((v) => v.key === tk);
                              if (!tv) return null;
                              const value = state.scannerVars[tk] ?? tv.default;
                              return (
                                <FilterRow
                                  key={tk}
                                  label={tv.label}
                                  unit={varUnit(tv)}
                                  dirty={String(value) !== String(tv.default)}
                                  onReset={() => resetVar(tv)}
                                  control={
                                    <input
                                      type="number"
                                      step="any"
                                      className="field font-mono"
                                      value={String(value)}
                                      onChange={(e) => setVar(tk, e.target.value === "" ? 0 : Number(e.target.value))}
                                    />
                                  }
                                />
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Section>
            );
          }
          return (
            <Section
              key={g.group}
              title={g.group === "EP" ? "Scan" : g.group}
              open={openGroups[g.group] ?? false}
              onToggle={(open) => setOpenGroups((prev) => ({ ...prev, [g.group]: open }))}
            >
              <div className="space-y-3">
                {g.fields.map((v) => {
                  const value = state.scannerVars[v.key] ?? v.default;
                  return (
                    <FilterField
                      key={v.key}
                      v={v}
                      value={value}
                      dirty={String(value) !== String(v.default)}
                      onReset={() => resetVar(v)}
                      onChange={(val) => setVar(v.key, val)}
                    />
                  );
                })}
              </div>
            </Section>
          );
        })}

        {error && (
          <div className="rounded-md border border-down-600/40 bg-down-600/10 px-3 py-2 text-xs text-down-500">
            {error}
          </div>
        )}
        {runId && runTerminal !== "idle" && <LiveRunStatus runId={runId} events={events} runTerminal={runTerminal} />}
      </div>

      {/* Results panel */}
      <section className="panel flex min-h-0 flex-col">
        <div className="flex flex-wrap items-center gap-3 border-b border-ink-800/60 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Scanner results</h2>
            <p className="text-xs text-slate-600">
              {state.scanRows.length} survivor{state.scanRows.length === 1 ? "" : "s"} ·{" "}
              {FAMILY_LABELS[state.family]} detection
            </p>
          </div>
          {zhaoBanner && (
            <div
              className="rounded-md border border-accent-600/30 bg-accent-600/10 px-3 py-1.5 text-xs text-slate-300"
              title="Benchmark context — informational only, never a market-regime block."
            >
              {zhaoBanner.benchSymbol} today {fmtPct(zhaoBanner.benchPct)} · {zhaoBanner.aboveSma}/
              {zhaoBanner.total} survivors hold above SMA20
            </div>
          )}
          <button
            type="button"
            className="btn-primary px-4 py-1.5 text-sm"
            disabled={busy || running || !universeReady}
            onClick={startScan}
          >
            {running ? "Scanning…" : busy ? "Starting…" : state.scanRows.length > 0 ? "Re-run scan" : "Run scan"}
          </button>
          <input
            className="field ml-auto w-52 px-2.5 py-1.5 font-mono text-sm"
            placeholder="Search symbol…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {chips.length > 0 && (
          <ChipRow>
            {chips.map((c) => (
              <span
                key={c.id}
                role="button"
                tabIndex={0}
                onClick={() => jumpTo(c.group)}
                onKeyDown={(e) => e.key === "Enter" && jumpTo(c.group)}
                className="inline-flex items-center gap-1.5 rounded-md border border-accent-600/40 bg-accent-600/10 px-2 py-0.5 text-2xs font-medium text-accent-300 hover:bg-accent-600/20"
              >
                {c.label}
              </span>
            ))}
          </ChipRow>
        )}

        {error && (
          <div className="border-b border-ink-800/60 px-4 py-2 text-xs text-down-500">{error}</div>
        )}

        {state.scanRows.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
            {running || busy ? (
              <>
                <div className="h-2 w-24 animate-pulse rounded bg-ink-700" />
                <div className="h-2 w-40 animate-pulse rounded bg-ink-800" />
                <p className="text-xs text-slate-600">Scanning the universe…</p>
              </>
            ) : (
              <>
                <p className="text-sm text-slate-400">
                  {runTerminal === "succeeded"
                    ? "No survivors passed the scan."
                    : runTerminal === "failed"
                      ? "Run failed — see the activity feed."
                      : "Configure filters and run the scan to populate results."}
                </p>
                {!universeReady && (
                  <p className="text-xs text-slate-600">Add symbols to the universe in the previous phase first.</p>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-ink-900 text-2xs uppercase tracking-wider text-slate-500">
                  <tr>
                    {columns.map((c) => (
                      <th
                        key={c.key}
                        className={`whitespace-nowrap px-3 py-2 font-medium ${c.numeric ? "text-right" : ""}`}
                      >
                        <button
                          type="button"
                          onClick={() => toggleSort(c.key)}
                          className={`hover:text-slate-300 ${sortKey === c.key ? "text-accent-400" : ""}`}
                        >
                          {c.label}
                          {sortKey === c.key && (sortDesc ? " ↓" : " ↑")}
                        </button>
                      </th>
                    ))}
                    <th className="px-3 py-2 font-medium">Evidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-800/60">
                  {rows.map((r) => {
                    const symbol = String(r.symbol ?? "");
                    return (
                      <tr key={symbol} className="hover:bg-ink-850/60">
                        <td className="whitespace-nowrap px-3 py-1.5 font-mono font-medium text-slate-100">{symbol}</td>
                        {columns.slice(1).map((c) => (
                          <td
                            key={c.key}
                            className={`whitespace-nowrap px-3 py-1.5 font-mono tnum ${
                              c.numeric ? "text-right text-slate-300" : "text-slate-300"
                            }`}
                          >
                            {c.key === "rating" || c.key === "structural_rating" || c.key === "strength" ? (
                              <span className="text-accent-400">{stars(rowRating(r))}</span>
                            ) : c.key === "variant" ? (
                              <span>{String(r[c.key] ?? "—")}</span>
                            ) : c.key === "features_held" ? (
                              <SetupCell features={r} />
                            ) : state.family === "zhao" && c.key === "streak" ? (
                              <span>{streakLabel(r[c.key])}</span>
                            ) : (
                              fmtCell(r[c.key], c)
                            )}
                          </td>
                        ))}
                        <td className="max-w-[280px] px-3 py-1.5">
                          <ul className="space-y-0.5 text-2xs leading-snug text-slate-500">
                            {rowExplanation(state.family, r).map((line, i) => (
                              <li key={i} className="truncate" title={line}>
                                {line}
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="border-t border-ink-800 px-4 py-2 font-mono text-2xs text-slate-600">
              {rows.length} / {state.scanRows.length} rows
              {sortKey ? ` · sorted by ${sortLabel ?? sortKey} ${sortDesc ? "desc" : "asc"}` : ""}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

function SetupCell({ features }: { features: Record<string, unknown> }) {
  const held = Number(features.features_held ?? 0);
  const marks = EP_FEATURES.map((f) => (features[f.key] === true ? "✓" : "·")).join("");
  const b = features.passes_baseline === true;
  const s = features.passes_strict === true;
  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-xs"
      title={`Features: ${marks}\nGates: Baseline ${b ? "✓" : "✗"} · Strict ${s ? "✓" : "✗"}`}
      aria-label={`${held}/${EP_FEATURES.length} features held; Baseline ${b ? "pass" : "fail"}; Strict ${s ? "pass" : "fail"}`}
    >
      <span className={held > 0 ? "text-up-500" : "text-slate-600"}>{held}</span>
      <span className="text-slate-700">/</span>
      <span className="text-slate-500">{EP_FEATURES.length}</span>
      <span className="text-slate-700">·</span>
      <span className={b ? "text-up-500" : "text-slate-600"}>B{b ? "✓" : "✗"}</span>
      <span className={s ? "text-up-500" : "text-slate-600"}>S{s ? "✓" : "✗"}</span>
    </span>
  );
}

function FilterField({
  v,
  value,
  dirty,
  onReset,
  onChange,
}: {
  v: VariableDef;
  value: string | number | boolean;
  dirty?: boolean;
  onReset?: () => void;
  onChange: (val: string | number | boolean) => void;
}) {
  const id = `var-${v.key}`;
  if (v.kind === "boolean") {
    return (
      <FilterRow
        label={v.label}
        dirty={dirty}
        onReset={onReset}
        control={
          <div className="flex items-center">
            <Switch checked={Boolean(value)} onChange={onChange} />
          </div>
        }
      />
    );
  }
  if (v.kind === "select") {
    return (
      <FilterRow label={v.label} dirty={dirty} onReset={onReset}
        control={
          <div className="flex flex-wrap gap-1">
            {(v.options ?? []).map((o) => {
              const active = String(value) === o;
              return (
                <button
                  key={o}
                  type="button"
                  onClick={() => onChange(o)}
                  className={`rounded px-2 py-1 text-xs font-medium transition-colors duration-150 ${
                    active
                      ? "bg-accent-600 text-ink-950"
                      : "border border-ink-700 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {o}
                </button>
              );
            })}
          </div>
        }
      />
    );
  }
  return (
    <FilterRow
      label={v.label}
      unit={varUnit(v)}
      dirty={dirty}
      onReset={onReset}
      control={
        <input
          id={id}
          type="number"
          step="any"
          className="field font-mono"
          value={String(value)}
          onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
        />
      }
    />
  );
}

function stars(rating: number): string {
  return "★".repeat(Math.max(0, Math.min(5, Math.round(rating)))) || "—";
}

function fmtCell(value: unknown, col: Column): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (col.fmt && !Number.isNaN(n)) {
    switch (col.fmt) {
      case "usd":
        return fmtCompact(n, { currency: true });
      case "pct":
        return fmtCompact(n, { digits: 1, suffix: "%" });
      case "ratio":
        return fmtCompact(n, { digits: 1, suffix: "×" });
      case "num":
        return fmtCompact(n, { digits: 0 });
    }
  }
  return String(value);
}
