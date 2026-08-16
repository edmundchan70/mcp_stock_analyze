"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Link from "next/link";

import { MergeTable } from "@/components/MergeTable";
import {
  createRun,
  deleteComponentTemplate,
  deleteDefinition,
  listComponentTemplates,
  listDefinitions,
  listTools,
  previewRun,
  saveComponentTemplate,
  saveDefinition,
  subscribeToRunEvents,
} from "@/lib/api";
import { UNIVERSE_ID, defaultsFor, isWireValid, visibleVars } from "@/lib/graph";
import type {
  ComponentTemplate,
  GraphDefinition,
  MergeTable as MergeTableData,
  PipelineDefinition,
  PreviewEstimate,
  RunEvent,
  ToolSpec,
  VariableDef,
} from "@/lib/types";

const TOOL_COLORS: Record<string, { border: string; text: string; dot: string }> = {
  universe: { border: "border-slate-500/60", text: "text-slate-300", dot: "bg-slate-300" },
  scanner: { border: "border-amber-500/60", text: "text-amber-400", dot: "bg-amber-400" },
  quant: { border: "border-violet-500/60", text: "text-violet-400", dot: "bg-violet-400" },
  search: { border: "border-sky-500/60", text: "text-sky-400", dot: "bg-sky-400" },
  report: { border: "border-emerald-500/60", text: "text-emerald-400", dot: "bg-emerald-400" },
};

const EDGE_COLORS: Record<string, string> = {
  universe: "#94a3b8",
  scanner: "#f59e0b",
  quant: "#8b5cf6",
  search: "#0ea5e9",
  report: "#10b981",
};

const FAMILY_LABELS: Record<string, string> = { ep: "EP", vcp: "VCP", bo: "BO", custom: "Custom" };
const PALETTE_IDS = ["scanner", "quant", "search", "report"] as const;

const PRESET_NAMES = new Set(["Daily VCP Scan", "Daily BO Scan", "Daily EP Scan"]);

const UNIVERSE_SPEC: ToolSpec = {
  id: UNIVERSE_ID,
  name: "Universe",
  description: "Paste / sweep / Force Include",
  phase: 0,
  inputs: [],
  outputs: [{ id: "out", type: "symbolkey", required: true, label: "symbols" }],
  variables: [],
};

interface NodeData extends Record<string, unknown> {
  component: ToolSpec;
  variables: Record<string, string | number | boolean>;
}

function ToolNode({ data, selected }: NodeProps) {
  const d = data as NodeData;
  const def = d.component;
  const colors = TOOL_COLORS[def.id] ?? TOOL_COLORS.universe;
  const family = d.variables.family as string | undefined;
  const caption = family ? FAMILY_LABELS[family] ?? String(family) : def.description;

  return (
    <div
      className={`min-w-[190px] rounded-lg border ${colors.border} ${
        selected ? "ring-2 ring-cyan-500/70" : ""
      } bg-slate-900 shadow-lg`}
    >
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <span className={`h-2 w-2 rounded-full ${colors.dot}`} />
          {def.name}
        </span>
        {def.id !== UNIVERSE_ID && (
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${colors.text} bg-slate-800`}>
            R{def.phase}
          </span>
        )}
      </div>
      <div className="px-3 py-1 text-[11px] text-slate-500">{caption}</div>
      <div className="flex items-center justify-between px-3 py-2 pt-1">
        <div className="flex flex-col gap-1.5">
          {def.inputs.map((p) => (
            <div key={p.id} className="relative flex items-center gap-2">
              <Handle
                type="target"
                position={Position.Left}
                id={p.id}
                className="!relative !left-0 !translate-x-0 !transform-none"
                style={{ width: 10, height: 10, background: p.required ? "#22d3ee" : "#64748b" }}
              />
              <span className="text-[11px] text-slate-400">
                {p.label}
                {!p.required && <span className="text-slate-600"> (opt)</span>}
              </span>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-1.5">
          {def.outputs.map((p) => (
            <div key={p.id} className="relative flex items-center justify-end gap-2">
              <span className="text-[11px] text-slate-400">{p.label}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={p.id}
                className="!relative !right-0 !translate-x-0 !transform-none"
                style={{ width: 10, height: 10, background: "#22d3ee" }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const nodeTypes = { phase: ToolNode };

function toRfNode(n: { id: string; type: string; position: { x: number; y: number }; variables: Record<string, string | number | boolean> }, tools: Record<string, ToolSpec>): Node {
  const component = n.type === UNIVERSE_ID ? UNIVERSE_SPEC : tools[n.type];
  return {
    id: n.id,
    type: "phase",
    position: n.position,
    deletable: n.type === UNIVERSE_ID ? false : true,
    data: { component: component ?? UNIVERSE_SPEC, variables: n.variables ?? {} },
  } as Node;
}

export function GraphEditor() {
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [definitions, setDefinitions] = useState<PipelineDefinition[]>([]);
  const [templates, setTemplates] = useState<ComponentTemplate[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [defsLoaded, setDefsLoaded] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const [graphName, setGraphName] = useState("");
  const [currentDefId, setCurrentDefId] = useState<string | null>(null);
  const [graphPick, setGraphPick] = useState("");
  const [graphDefaults, setGraphDefaults] = useState<{ universe_source?: string }>({});

  const [tplName, setTplName] = useState("");
  const [tplPick, setTplPick] = useState("");

  const [universeText, setUniverseText] = useState("");
  const [universeSource, setUniverseSource] = useState<"paste" | "snapshot">("paste");
  const [snapshotScanId, setSnapshotScanId] = useState("");
  const [runName, setRunName] = useState("");

  const [runId, setRunId] = useState<string | null>(null);
  const [nodeStatus, setNodeStatus] = useState<Record<string, { status: string; kept?: number }>>({});
  const [mergeTable, setMergeTable] = useState<MergeTableData | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const [preview, setPreview] = useState<PreviewEstimate | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const nextId = useRef(10);
  const toolsById = useMemo(() => new Map(tools.map((t) => [t.id, t])), [tools]);

  // ── initial load ──────────────────────────────────────────────────
  useEffect(() => {
    listTools()
      .then(setTools)
      .catch((e) => setLoadError(`tools: ${String(e)}`));
    listDefinitions()
      .then(setDefinitions)
      .catch((e) => setLoadError((p) => [p, `definitions: ${String(e)}`].filter(Boolean).join(" · ")))
      .finally(() => setDefsLoaded(true));
    listComponentTemplates()
      .then(setTemplates)
      .catch((e) => setLoadError((p) => [p, `templates: ${String(e)}`].filter(Boolean).join(" · ")));
  }, []);

  // Auto-load the VCP preset once tools + definitions are ready; fall back to
  // a seeded single-lane graph when the presets haven't been seeded yet.
  useEffect(() => {
    if (tools.length === 0 || !defsLoaded || nodes.length > 0) return;
    const vcpPreset = definitions.find((d) => d.name === "Daily VCP Scan");
    if (vcpPreset) {
      loadDefinition(vcpPreset.id);
    } else {
      seedDefaultGraph();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tools.length, defsLoaded]);

  function seedDefaultGraph() {
    const sc = toolsById.get("scanner");
    const rp = toolsById.get("report");
    if (!sc || !rp) return;
    const n = (id: string, def: ToolSpec, x: number, y: number, variables?: Record<string, string | number | boolean>): Node => ({
      id,
      type: "phase",
      position: { x, y },
      deletable: id !== UNIVERSE_ID,
      data: { component: def, variables: variables ?? defaultsFor(def) },
    });
    setNodes([
      n(UNIVERSE_ID, UNIVERSE_SPEC, 40, 200),
      n("sc_1", sc, 300, 40, { ...defaultsFor(sc), family: "vcp" }),
      n("r_1", rp, 600, 40),
    ]);
    setEdges([
      { id: "e1", source: UNIVERSE_ID, sourceHandle: "out", target: "sc_1", targetHandle: "universe" },
      { id: "e2", source: "sc_1", sourceHandle: "bucket", target: "r_1", targetHandle: "structural" },
    ]);
  }

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const isValidConnection = useCallback(
    (conn: Edge | Connection): boolean =>
      isWireValid(nodeById.get(conn.source), nodeById.get(conn.target), conn.sourceHandle, conn.targetHandle),
    [nodeById],
  );

  const onConnect = useCallback((conn: Connection) => setEdges((eds) => addEdge(conn, eds)), [setEdges]);

  const styledEdges = useMemo<Edge[]>(
    () =>
      edges.map((e) => {
        const srcDef = nodeById.get(e.source)?.data as NodeData | undefined;
        return {
          ...e,
          style: {
            stroke: EDGE_COLORS[srcDef?.component.id ?? "universe"] ?? "#94a3b8",
            strokeWidth: 1.5,
          },
        };
      }),
    [edges, nodeById],
  );

  // ── node / inspector actions ──────────────────────────────────────

  function addComponent(componentId: string) {
    const def = toolsById.get(componentId);
    if (!def) return;
    const maxX = nodes.reduce((m, n) => Math.max(m, n.position.x), 0);
    const nodeId = `${componentId}_${nextId.current++}`;
    const newNode: Node = {
      id: nodeId,
      type: "phase",
      position: { x: Math.max(300, maxX) + 140, y: 60 + (nodes.length % 6) * 80 },
      data: { component: def, variables: defaultsFor(def) },
    };
    const newEdges: Edge[] = [];
    if (componentId === "scanner") {
      const universe = nodes.find((n) => n.id === UNIVERSE_ID);
      if (universe) {
        newEdges.push({
          id: `e_${nodeId}`,
          source: UNIVERSE_ID,
          sourceHandle: "out",
          target: nodeId,
          targetHandle: "universe",
        });
      }
    }
    setNodes((ns) => [...ns, newNode]);
    setEdges((es) => [...es, ...newEdges]);
    setSelectedId(nodeId);
  }

  function updateVariable(key: string, value: string | number | boolean) {
    if (!selectedId) return;
    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== selectedId) return n;
        const data = n.data as NodeData;
        return { ...n, data: { ...data, variables: { ...data.variables, [key]: value } } };
      }),
    );
  }

  function toggleGroup(name: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function renderVariable(v: VariableDef, value: string | number | boolean) {
    if (v.kind === "boolean") {
      return (
        <label key={v.key} className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={Boolean(value)} onChange={(e) => updateVariable(v.key, e.target.checked)} />
          {v.label}
        </label>
      );
    }
    if (v.kind === "select") {
      return (
        <div key={v.key}>
          <label className="mb-1 block text-xs font-medium text-slate-400">{v.label}</label>
          <select
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
            value={String(value)}
            onChange={(e) => updateVariable(v.key, e.target.value)}
          >
            {v.options?.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
      );
    }
    return (
      <div key={v.key}>
        <label className="mb-1 block text-xs font-medium text-slate-400">{v.label}</label>
        <input
          type={v.kind === "number" ? "number" : "text"}
          className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
          value={String(value)}
          onChange={(e) => updateVariable(v.key, v.kind === "number" ? Number(e.target.value) : e.target.value)}
        />
      </div>
    );
  }

  function renderGrouped(vars: VariableDef[], values: Record<string, string | number | boolean>) {
    const groups: { name: string; vars: VariableDef[] }[] = [];
    for (const v of vars) {
      const last = groups[groups.length - 1];
      if (last && last.name === v.group) last.vars.push(v);
      else groups.push({ name: v.group, vars: [v] });
    }
    return groups.map((g) => (
      <div key={g.name} className="rounded-md border border-slate-800">
        <button
          type="button"
          onClick={() => toggleGroup(g.name)}
          className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800/50"
        >
          <span>{g.name}</span>
          <span className="text-slate-500">{collapsed.has(g.name) ? "▸" : "▾"}</span>
        </button>
        {!collapsed.has(g.name) && (
          <div className="space-y-2 px-3 pb-3 pt-1">{g.vars.map((v) => renderVariable(v, values[v.key] ?? v.default))}</div>
        )}
      </div>
    ));
  }

  // ── graph definitions (T20/T25) ───────────────────────────────────

  function serializeGraph(): GraphDefinition {
    const graph: GraphDefinition = {
      name: graphName || "untitled",
      nodes: nodes.map((n) => ({
        id: n.id,
        type: (n.data as NodeData).component.id,
        position: n.position,
        variables: (n.data as NodeData).variables,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle ?? "out",
        target: e.target,
        targetHandle: e.targetHandle ?? "in",
      })),
    };
    if (Object.keys(graphDefaults).length > 0) {
      graph.defaults = { ...graphDefaults };
    }
    return graph;
  }

  async function saveGraph() {
    if (nodes.length === 0) return;
    const graph = serializeGraph();
    const saved = await saveDefinition({ name: graph.name, graph }, currentDefId ?? undefined);
    setCurrentDefId(saved.id);
    setDefinitions(await listDefinitions());
  }

  async function loadDefinition(id: string) {
    const def = definitions.find((d) => d.id === id);
    if (!def) return;
    setNodes(def.graph.nodes.map((n) => toRfNode(n, Object.fromEntries(toolsById))));
    setEdges(
      def.graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle,
        target: e.target,
        targetHandle: e.targetHandle,
      })),
    );
    setGraphName(def.name);
    setCurrentDefId(def.id);
    setSelectedId(null);
    const defaults = def.graph.defaults ?? {};
    setGraphDefaults(defaults);
    setUniverseSource(defaults.universe_source === "snapshot" ? "snapshot" : "paste");
  }

  async function removeDefinition(id: string) {
    await deleteDefinition(id);
    setDefinitions(await listDefinitions());
    if (currentDefId === id) setCurrentDefId(null);
  }

  // ── component templates (T25) ─────────────────────────────────────

  async function saveTpl() {
    if (!selectedId || !tplName.trim()) return;
    const sel = nodes.find((n) => n.id === selectedId);
    if (!sel) return;
    const data = sel.data as NodeData;
    await saveComponentTemplate({ name: tplName.trim(), component_id: data.component.id, variables: data.variables });
    setTemplates(await listComponentTemplates());
    setTplName("");
  }

  async function applyTpl(id: string) {
    const t = templates.find((x) => x.id === id);
    if (!t || !selectedId) return;
    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== selectedId) return n;
        const data = n.data as NodeData;
        return { ...n, data: { ...data, variables: { ...t.variables } } };
      }),
    );
  }

  async function removeTpl(id: string) {
    await deleteComponentTemplate(id);
    setTemplates(await listComponentTemplates());
  }

  // ── run + preview (T22/T26) ───────────────────────────────────────

  function runBody(): Record<string, unknown> {
    return {
      name: runName || graphName || "graph-run",
      pipeline_type: "daily_bo_scan", // required by schema; graph path ignores it
      graph: serializeGraph(),
      force_symbols: universeSource === "paste" ? universeText : "",
      universe_source: universeSource,
      universe_scan_id: universeSource === "snapshot" ? snapshotScanId : null,
    };
  }

  async function estimate() {
    setPreviewError(null);
    try {
      const res = await previewRun(runBody());
      setPreview(res.estimate);
      setPreviewOpen(true);
    } catch (e) {
      setPreviewError(String(e));
    }
  }

  async function runGraph() {
    if (nodes.length === 0) return;
    setRunError(null);
    setMergeTable(null);
    setNodeStatus({});
    try {
      const run = await createRun(runBody());
      setRunId(run.id);
      subscribeToRunEvents(run.id, (e: RunEvent) => handleRunEvent(e));
    } catch (e) {
      setRunError(String(e));
    }
  }

  function handleRunEvent(e: RunEvent) {
    if (e.type === "node" && e.node_id) {
      setNodeStatus((prev) => ({ ...prev, [e.node_id!]: { status: e.status ?? "running", kept: e.kept } }));
    }
    if (e.type === "done") {
      if (e.merge_table) setMergeTable(e.merge_table);
    }
    if (e.type === "failed") {
      setRunError(e.error ?? "run failed");
    }
  }

  const selected = nodes.find((n) => n.id === selectedId);
  const selectedData = selected ? (selected.data as NodeData) : null;
  const activeNodeStatuses = nodes
    .filter((n) => n.id !== UNIVERSE_ID)
    .map((n) => ({ id: n.id, tool: (n.data as NodeData).component, status: nodeStatus[n.id] }));

  return (
    <main className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-6 py-3">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
            ← Dashboard
          </Link>
          <h1 className="text-lg font-bold">Component Pipeline Graph</h1>
          {loadError && <span className="text-xs text-amber-400">{loadError}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <input
            value={graphName}
            onChange={(e) => setGraphName(e.target.value)}
            placeholder="graph name"
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
          <select
            value={graphPick}
            onChange={(e) => setGraphPick(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          >
            <option value="">Definitions…</option>
            <optgroup label="Daily presets">
              {definitions
                .filter((d) => PRESET_NAMES.has(d.name))
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
            </optgroup>
            {definitions
              .filter((d) => !PRESET_NAMES.has(d.name))
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
          </select>
          <button
            onClick={() => graphPick && loadDefinition(graphPick)}
            className="rounded-md bg-slate-800 px-2.5 py-1 font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
            disabled={!graphPick}
          >
            Load
          </button>
          <button
            onClick={saveGraph}
            className="rounded-md bg-cyan-600 px-2.5 py-1 font-medium text-slate-950 hover:bg-cyan-500"
          >
            {currentDefId ? "Update" : "Save graph"}
          </button>
          {currentDefId && (
            <button
              onClick={() => removeDefinition(currentDefId)}
              className="rounded-md bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700"
            >
              Delete
            </button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Left palette */}
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-slate-800 bg-slate-900/60 p-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Add component</h2>
          <div className="mt-2 space-y-2">
            {PALETTE_IDS.map((id) => {
              const c = toolsById.get(id);
              if (!c) return null;
              const colors = TOOL_COLORS[id] ?? TOOL_COLORS.universe;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => addComponent(id)}
                  className="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-left hover:border-slate-600"
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${colors.dot}`} />
                    <span className="text-sm font-semibold text-slate-200">
                      {c.name} <span className={`text-[10px] ${colors.text}`}>R{c.phase}</span>
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-slate-500">{c.description}</p>
                </button>
              );
            })}
          </div>
          <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
            Universe is auto-seeded as the start node. New Scanners wire from its{" "}
            <span className="font-mono text-slate-400">out</span> port automatically.
          </p>
        </aside>

        {/* Canvas */}
        <div className="relative min-w-0 flex-1">
          <ReactFlow
            nodes={nodes}
            edges={styledEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            nodeTypes={nodeTypes}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1e293b" gap={24} />
            <Controls className="!bg-slate-900" />
          </ReactFlow>

          <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-slate-800 bg-slate-900/90 px-3 py-2 text-[11px] text-slate-400">
            <span className="font-semibold text-slate-300">Legend</span>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="text-slate-300">Universe</span>
              <span className="text-amber-400">Scanner</span>
              <span className="text-violet-400">Quant</span>
              <span className="text-sky-400">AI Search</span>
              <span className="text-emerald-400">Report</span>
            </div>
          </div>
        </div>

        {/* Inspector */}
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-slate-800 bg-slate-900/60 p-4">
          {/* Universe binding + run */}
          <section className="rounded-md border border-slate-800 p-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Universe</h2>
            <select
              value={universeSource}
              onChange={(e) => setUniverseSource(e.target.value as "paste" | "snapshot")}
              className="mt-2 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
            >
              <option value="paste">Paste symbols</option>
              <option value="snapshot">Market snapshot sweep</option>
            </select>
            {universeSource === "paste" ? (
              <textarea
                value={universeText}
                onChange={(e) => setUniverseText(e.target.value)}
                placeholder="AAPL, NVDA, MSFT…"
                className="mt-2 h-24 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
              />
            ) : (
              <input
                value={snapshotScanId}
                onChange={(e) => setSnapshotScanId(e.target.value)}
                placeholder="scan id"
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
              />
            )}
            <div className="mt-3 flex gap-2">
              <button
                onClick={estimate}
                className="flex-1 rounded-md bg-slate-800 px-2 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700"
              >
                Preview
              </button>
              <button
                onClick={runGraph}
                className="flex-1 rounded-md bg-emerald-600 px-2 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-500"
              >
                Run graph
              </button>
            </div>
            {runId && (
              <Link href={`/runs/${runId}`} className="mt-2 block text-xs text-cyan-300 hover:underline">
                View run {runId.slice(0, 8)} →
              </Link>
            )}
            {runError && <p className="mt-2 text-xs text-rose-400">{runError}</p>}
            {previewError && <p className="mt-2 text-xs text-rose-400">{previewError}</p>}
          </section>

          {/* Node inspector */}
          {selectedData ? (
            <div className="mt-4">
              <h2 className="text-sm font-semibold text-slate-200">{selectedData.component.name}</h2>
              <p className="mt-0.5 text-[11px] text-slate-500">
                {selectedData.component.id === UNIVERSE_ID
                  ? "Bound at run time (paste / sweep / Force Include)"
                  : `R${selectedData.component.phase} · ${selectedData.component.description}`}
              </p>
              {selectedData.component.id !== UNIVERSE_ID && (
                <div className="mt-4 space-y-3">
                  {selectedData.component.variables.length === 0 ? (
                    <p className="text-sm text-slate-500">No variables.</p>
                  ) : (
                    renderGrouped(visibleVars(selectedData.component, selectedData.variables), selectedData.variables)
                  )}
                </div>
              )}

              {selectedData.component.id !== UNIVERSE_ID && (
                <div className="mt-6 border-t border-slate-800 pt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Component template</h3>
                  <div className="mt-2 flex gap-2">
                    <input
                      value={tplName}
                      onChange={(e) => setTplName(e.target.value)}
                      placeholder="template name"
                      className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    />
                    <button
                      onClick={saveTpl}
                      className="rounded-md bg-slate-800 px-2 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700"
                    >
                      Save
                    </button>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <select
                      value={tplPick}
                      onChange={(e) => setTplPick(e.target.value)}
                      className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    >
                      <option value="">Saved components…</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => tplPick && applyTpl(tplPick)}
                      className="rounded-md bg-slate-800 px-2 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
                      disabled={!tplPick}
                    >
                      Apply
                    </button>
                    <button
                      onClick={() => tplPick && removeTpl(tplPick)}
                      className="rounded-md px-1 py-1 text-xs text-rose-400 hover:bg-slate-800"
                      title="Delete template"
                    >
                      ×
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-500">Select a component to edit its settings.</p>
          )}

          {/* Run progress + results */}
          <section className="mt-6 border-t border-slate-800 pt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Run progress</h2>
            <div className="mt-2 space-y-1.5">
              {activeNodeStatuses.map((n) => (
                <div key={n.id} className="flex items-center justify-between text-xs">
                  <span className="text-slate-300">
                    {n.tool.name} <span className="text-slate-600">{n.id}</span>
                  </span>
                  {n.status ? (
                    <span
                      className={
                        n.status.status === "ok"
                          ? "text-emerald-400"
                          : n.status.status === "error"
                            ? "text-rose-400"
                            : "text-amber-400"
                      }
                    >
                      {n.status.status}
                      {typeof n.status.kept === "number" ? ` (${n.status.kept})` : ""}
                    </span>
                  ) : (
                    <span className="text-slate-600">waiting</span>
                  )}
                </div>
              ))}
              {activeNodeStatuses.length === 0 && <p className="text-xs text-slate-600">No nodes yet.</p>}
            </div>
          </section>

          <section className="mt-6 border-t border-slate-800 pt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Lane merge</h2>
            <div className="mt-3">
              <MergeTable table={mergeTable} />
            </div>
          </section>
        </aside>
      </div>

      {/* Preview estimate modal */}
      {previewOpen && preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-6" onClick={() => setPreviewOpen(false)}>
          <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-5" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-sm font-semibold text-slate-100">Run estimate</h2>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md border border-slate-800 p-2">
                <div className="text-lg font-bold text-slate-100">{preview.symbols}</div>
                <div className="text-[10px] text-slate-500">symbols</div>
              </div>
              <div className="rounded-md border border-slate-800 p-2">
                <div className="text-lg font-bold text-slate-100">{preview.duration}</div>
                <div className="text-[10px] text-slate-500">wall time</div>
              </div>
              <div className="rounded-md border border-slate-800 p-2">
                <div className="text-lg font-bold text-slate-100">${preview.cost.toFixed(2)}</div>
                <div className="text-[10px] text-slate-500">est. cost</div>
              </div>
            </div>
            {preview.warnings.length > 0 && (
              <div className="mt-3 space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
                {preview.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-amber-300">
                    ⚠ {w}
                  </p>
                ))}
              </div>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <button onClick={() => setPreviewOpen(false)} className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-700">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
