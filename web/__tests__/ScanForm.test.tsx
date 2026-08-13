import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ScanForm } from "@/components/ScanForm";

describe("ScanForm", () => {
  it("requires symbols before submitting", () => {
    const onSubmit = vi.fn();
    render(<ScanForm onSubmit={onSubmit} submitting={false} />);
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/paste at least one ticker/i)).toBeInTheDocument();
  });

  it("shows BO profile field by default", () => {
    render(<ScanForm onSubmit={vi.fn()} submitting={false} />);
    expect(screen.getByLabelText(/funnel profile/i)).toBeInTheDocument();
  });

  it("shows EP-specific fields only for EP", () => {
    render(<ScanForm onSubmit={vi.fn()} submitting={false} />);
    fireEvent.change(screen.getByLabelText(/pipeline/i), { target: { value: "daily_ep_scan" } });
    expect(screen.getByLabelText(/gate bucket/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/funnel profile/i)).not.toBeInTheDocument();
  });

  it("shows apply-gates for VCP", () => {
    render(<ScanForm onSubmit={vi.fn()} submitting={false} />);
    fireEvent.change(screen.getByLabelText(/pipeline/i), { target: { value: "daily_vcp_scan" } });
    expect(screen.getByLabelText(/apply gates/i)).toBeInTheDocument();
  });

  it("submits the correct BO body", () => {
    const onSubmit = vi.fn();
    render(<ScanForm onSubmit={onSubmit} submitting={false} />);
    fireEvent.change(screen.getByLabelText(/run name/i), { target: { value: "nightly" } });
    fireEvent.change(screen.getByLabelText(/symbols/i), { target: { value: "AAPL, MSFT" } });
    fireEvent.change(screen.getByLabelText(/funnel profile/i), { target: { value: "moderate-lose" } });
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "nightly",
        pipeline_type: "daily_bo_scan",
        force_symbols: "AAPL, MSFT",
        bo_profile: "moderate-lose",
        apply_gates: true,
      }),
    );
  });
});
