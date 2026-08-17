import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  controlRun: vi.fn(),
  PIPELINE_LABELS: { daily_bo_scan: "Qullamaggie BO" },
}));

import { RunTable } from "@/components/RunTable";
import { controlRun } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const base = {
  id: "1",
  name: "graph-run",
  pipeline_type: "daily_bo_scan" as const,
  counts: null,
  error: null,
  started_at: "2026-08-13T00:00:00Z",
  finished_at: null,
};

describe("RunTable runtime controls", () => {
  beforeEach(() => {
    vi.mocked(controlRun).mockReset();
    vi.mocked(controlRun).mockResolvedValue(undefined);
  });

  it("renders a cancelled status", () => {
    render(<RunTable runs={[{ ...base, status: "cancelled" } as RunSummary]} />);
    expect(screen.getByText("cancelled")).toBeInTheDocument();
  });

  it("shows awaiting-confirmation controls and confirms proceed", async () => {
    const run = {
      ...base,
      status: "running",
      awaiting_confirmation: { node_id: "search_1", symbol_count: 120, tavily_estimate: 240 },
    } as RunSummary;
    render(<RunTable runs={[run]} />);

    expect(screen.getByText("awaiting confirmation")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Proceed" }));
    await waitFor(() => expect(controlRun).toHaveBeenCalledWith("1", "confirm", "search_1", "proceed"));
  });

  it("renders a cancel button for running runs and cancels", async () => {
    render(<RunTable runs={[{ ...base, status: "running" } as RunSummary]} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(controlRun).toHaveBeenCalled());
    expect(vi.mocked(controlRun).mock.calls[0].slice(0, 2)).toEqual(["1", "cancel"]);
  });
});
