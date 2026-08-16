export type PipelineType = "daily_ep_scan" | "daily_vcp_scan" | "daily_bo_scan";

// ── component graph editor (T13/T24) ────────────────────────────────

export type PortType = "symbolkey" | "scan_rows" | "filtered_rows" | "enriched_rows" | "report_rows";

export type VarKind = "number" | "boolean" | "select" | "text";

export interface PortDef {
  id: string;
  type: PortType;
  required: boolean;
  label: string;
}

export interface VariableDef {
  key: string;
  label: string;
  kind: VarKind;
  default: string | number | boolean;
  group: string;
  options?: string[];
}

export interface ToolSpec {
  id: string;
  name: string;
  description: string;
  phase: number;
  inputs: PortDef[];
  outputs: PortDef[];
  variables: VariableDef[];
}

export interface GraphNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  variables: Record<string, string | number | boolean>;
}

export interface GraphEdge {
  id: string;
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
}

export interface GraphDefinition {
  name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  defaults?: { universe_source?: string };
}

export interface ComponentTemplate {
  id: string;
  name: string;
  component_id: string;
  variables: Record<string, string | number | boolean>;
}

export interface PipelineDefinition {
  id: string;
  name: string;
  graph: GraphDefinition;
}

export interface MergeTableRow {
  symbol: string;
  exchange?: string;
  rating?: number;
  lanes?: string;
  [key: string]: unknown;
}

export interface MergeTable {
  columns: string[];
  rows: MergeTableRow[];
  count: number;
}

export interface PreviewEstimate {
  symbols: number;
  seconds: number;
  duration: string;
  cost: number;
  nodes: { node_id: string; tool_id: string; seconds: number; cost: number }[];
  warnings: string[];
}

export interface PreviewResponse {
  estimate: PreviewEstimate;
  graph: { name: string; nodes: number; edges: number };
}

export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed";

export interface RunSummary {
  id: string;
  name: string;
  pipeline_type: PipelineType;
  status: RunStatus;
  counts: Record<string, number> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  params: Record<string, unknown>;
  artifacts: Record<string, unknown>;
}

export interface RunEvent {
  type: "stage" | "stage_done" | "fail" | "ticker_begin" | "ticker" | "ticker_end" | "console" | "node" | "done" | "failed";
  text?: string;
  description?: string;
  total?: number;
  index?: number;
  symbol?: string;
  action?: string;
  error?: string;
  counts?: Record<string, number>;
  // graph runs (T22)
  node_id?: string;
  tool_id?: string;
  status?: string;
  kept?: number;
  merge_table?: MergeTable;
  degraded?: boolean;
}

export interface RatedStock {
  symbol: string;
  // EP shape
  ep_rating?: number;
  catalyst_type?: string | null;
  ep_rationale?: string | null;
  // VCP/BO shape
  final_rating?: number;
  variant?: string | null;
  sector?: string | null;
  cap_applied?: boolean;
  industry_group_strength_flag?: string | null;
  [key: string]: unknown;
}
