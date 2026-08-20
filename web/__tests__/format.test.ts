import { describe, expect, it } from "vitest";
import { fmtCompact, fmtPct, fmtRatio, fmtUsd } from "@/lib/format";

describe("fmtCompact", () => {
  it("compacts billions", () => {
    expect(fmtCompact(1_250_000_000)).toBe("1.3B");
    expect(fmtCompact(10_000_000_000)).toBe("10.0B");
  });

  it("compacts millions", () => {
    expect(fmtCompact(5_000_000)).toBe("5.0M");
    expect(fmtCompact(24_600_000)).toBe("24.6M");
  });

  it("compacts thousands", () => {
    expect(fmtCompact(1_500)).toBe("1.5K");
    expect(fmtCompact(123_456)).toBe("123.5K");
  });

  it("keeps 0–2 dp below 1e3", () => {
    expect(fmtCompact(12)).toBe("12");
    expect(fmtCompact(12.5)).toBe("12.5");
    expect(fmtCompact(12.345)).toBe("12.35");
    expect(fmtCompact(0)).toBe("0");
  });

  it("handles missing and non-numeric values", () => {
    expect(fmtCompact(null)).toBe("—");
    expect(fmtCompact(undefined)).toBe("—");
    expect(fmtCompact("")).toBe("—");
    expect(fmtCompact("n/a")).toBe("n/a");
  });

  it("supports currency and units", () => {
    expect(fmtCompact(5_000_000, { currency: true })).toBe("$5.0M");
    expect(fmtCompact(4.2, { digits: 1, suffix: "%" })).toBe("4.2%");
    expect(fmtCompact(3.5, { digits: 1, suffix: "×" })).toBe("3.5×");
  });
});

describe("fmt helpers", () => {
  it("fmtPct appends %", () => {
    expect(fmtPct(4.2)).toBe("4.2%");
    expect(fmtPct(0.5)).toBe("0.5%");
  });

  it("fmtRatio appends ×", () => {
    expect(fmtRatio(1.5)).toBe("1.5×");
  });

  it("fmtUsd prefixes $", () => {
    expect(fmtUsd(5_000_000)).toBe("$5.0M");
    expect(fmtUsd(12.34)).toBe("$12.34");
    expect(fmtUsd(1_000_000_000)).toBe("$1.0B");
  });
});
