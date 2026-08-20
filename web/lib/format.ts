/**
 * Compact number formatting shared across every results surface (scanner,
 * report, run tables, merge table, chart footers).
 *
 * TradingView-screener-style magnitudes:
 *   ≥1e9 → "1.2B", ≥1e6 → "4.5M", ≥1e3 → "12.3K", else 0–2 dp.
 * Optionally prefixed with "$" and/or suffixed with a unit ("%", "×").
 */

export interface FmtOptions {
  /** Decimals for magnitudes below 1e3 (default 0 for whole, 2 otherwise). */
  digits?: number;
  /** Decimals for K/M/B magnitudes (default 1). */
  compactDigits?: number;
  /** Prepend "$". */
  currency?: boolean;
  /** Trailing unit suffix, e.g. "%" or "×". */
  suffix?: string;
}

const DASH = "—";

export function fmtCompact(value: unknown, opts: FmtOptions = {}): string {
  const { digits = 2, compactDigits = 1, currency = false, suffix = "" } = opts;
  if (value === null || value === undefined || value === "") return DASH;
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);

  const prefix = currency ? "$" : "";
  const abs = Math.abs(n);
  let out: string;
  if (abs >= 1e9) out = `${(n / 1e9).toFixed(compactDigits)}B`;
  else if (abs >= 1e6) out = `${(n / 1e6).toFixed(compactDigits)}M`;
  else if (abs >= 1e3) out = `${(n / 1e3).toFixed(compactDigits)}K`;
  else out = n.toFixed(digits).replace(/\.?0+$/, "");
  return `${prefix}${out}${suffix}`;
}

export function fmtPct(value: unknown, digits = 1): string {
  return fmtCompact(value, { digits, suffix: "%" });
}

export function fmtRatio(value: unknown, digits = 1): string {
  return fmtCompact(value, { digits, suffix: "×" });
}

export function fmtUsd(value: unknown): string {
  return fmtCompact(value, { currency: true });
}
