import type { GraphDefinition, GraphEdge, GraphNode, PortType, ToolSpec, VariableDef } from "./types";

// Mirrors stock_analyze/tools/protocol.py — keep in sync.
export const INPUT_ACCEPTS: Record<PortType, PortType[]> = {
  symbolkey: ["symbolkey"],
  scan_rows: ["scan_rows"],
  filtered_rows: ["scan_rows", "filtered_rows"],
  enriched_rows: ["scan_rows", "filtered_rows", "enriched_rows"],
  report_rows: ["scan_rows", "filtered_rows", "enriched_rows"],
};

export const UNIVERSE_ID = "universe";

export interface NodeData extends Record<string, unknown> {
  component: ToolSpec;
  variables: Record<string, string | number | boolean>;
}

export function defaultsFor(def: ToolSpec): Record<string, string | number | boolean> {
  const v: Record<string, string | number | boolean> = {};
  for (const vd of def.variables) v[vd.key] = vd.default;
  return v;
}

export function scannerGroups(family: string): string[] {
  switch (family) {
    case "vcp":
      return ["Family", "VCP"];
    case "bo":
      return ["Family", "BO"];
    case "custom":
      return ["Family", "Custom"];
    default:
      return ["Family", "EP", "EP baseline", "EP strict"];
  }
}

export function visibleVars(def: ToolSpec, variables: Record<string, string | number | boolean>): VariableDef[] {
  if (def.id === "scanner") {
    const family = String(variables.family ?? "ep");
    const groups = scannerGroups(family);
    return def.variables.filter((v) => groups.includes(v.group));
  }
  return def.variables;
}

export function isWireValid(
  src: { data?: Record<string, unknown> } | undefined,
  tgt: { data?: Record<string, unknown> } | undefined,
  sourceHandle: string | null | undefined,
  targetHandle: string | null | undefined,
): boolean {
  if (!src || !tgt || src === tgt || !sourceHandle || !targetHandle) return false;
  const s = src.data as NodeData;
  const t = tgt.data as NodeData;
  const outPort = s.component?.outputs.find((p) => p.id === sourceHandle);
  const inPort = t.component?.inputs.find((p) => p.id === targetHandle);
  if (!outPort || !inPort) return false;
  return INPUT_ACCEPTS[inPort.type]?.includes(outPort.type) ?? false;
}

export function toGraphDefinition(nodes: GraphNode[], edges: GraphEdge[]): GraphDefinition {
  return { name: "", nodes, edges };
}

export function universeNodes(nodes: GraphNode[]): GraphNode[] {
  return nodes.filter((n) => n.type === UNIVERSE_ID);
}

export function componentNodes(nodes: GraphNode[]): GraphNode[] {
  return nodes.filter((n) => n.type !== UNIVERSE_ID);
}
