import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StarBadge } from "@/components/StarBadge";
import { ResultsTable } from "@/components/ResultsTable";

describe("StarBadge", () => {
  it("renders filled stars for a rating", () => {
    render(<StarBadge rating={4} />);
    expect(screen.getByText("★★★★")).toBeInTheDocument();
  });

  it("renders a dash for zero", () => {
    render(<StarBadge rating={0} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("ResultsTable", () => {
  it("renders VCP/BO rated stocks", () => {
    const artifacts = {
      agent3: {
        count: 1,
        stocks: [
          {
            symbol: "AAPL",
            final_rating: 5,
            variant: "classic",
            sector: "Tech",
            industry_group_strength_flag: "HOT_SECTOR",
            cap_applied: false,
          },
        ],
      },
    };
    render(<ResultsTable artifacts={artifacts} pipelineType="daily_bo_scan" />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("classic")).toBeInTheDocument();
    expect(screen.getByText("HOT_SECTOR")).toBeInTheDocument();
  });

  it("renders EP rated stocks", () => {
    const artifacts = {
      agent3: {
        count: 1,
        stocks: [{ symbol: "NVDA", ep_rating: 5, catalyst_type: "EARNINGS", ep_rationale: "beat" }],
      },
    };
    render(<ResultsTable artifacts={artifacts} pipelineType="daily_ep_scan" />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("EARNINGS")).toBeInTheDocument();
  });

  it("shows an empty state when there are no rated stocks", () => {
    render(<ResultsTable artifacts={{}} pipelineType="daily_bo_scan" />);
    expect(screen.getByText(/no rated stocks/i)).toBeInTheDocument();
  });
});
