export type PipelineType = "daily_ep_scan" | "daily_vcp_scan" | "daily_bo_scan";

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
  type: "stage" | "stage_done" | "fail" | "ticker_begin" | "ticker" | "ticker_end" | "console" | "done" | "failed";
  text?: string;
  description?: string;
  total?: number;
  index?: number;
  symbol?: string;
  action?: string;
  error?: string;
  counts?: Record<string, number>;
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
