import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  listRuns: vi.fn(),
  PIPELINE_LABELS: { daily_bo_scan: "Qullamaggie BO" },
}));

import Home from "@/app/page";
import { listRuns } from "@/lib/api";

describe("Home dashboard", () => {
  beforeEach(() => {
    vi.mocked(listRuns).mockReset();
  });

  it("lists runs from the API", async () => {
    vi.mocked(listRuns).mockResolvedValue([
      {
        id: "1",
        name: "nightly",
        pipeline_type: "daily_bo_scan",
        status: "succeeded",
        counts: { 5: 1 },
        error: null,
        started_at: "2026-08-13T00:00:00Z",
        finished_at: null,
      },
    ]);

    render(<Home />);
    await waitFor(() => expect(screen.getByText("nightly")).toBeInTheDocument());
    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /nightly/i })).toHaveAttribute("href", "/runs/1");
  });
});
