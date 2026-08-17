Type: prototype
Status: resolved

## Question

Rebuild the throwaway canvas stub for the component model: a **+ button** that adds one of 4 components (Scanner, Quant Filter/Gate, AI Search, Report), plus a left palette; selection-driven settings panels exposing full config — TradingView-screener style for Scanner, all gates/thresholds editable for Quant, full search settings for AI Search, report/caps fields for Report; **component + graph templates**; **mark-red** on param invalidation; SymbolKey **merge table**. Cheap and rough — for reaction, not production.

## Answer

Resolved in this session — built the component-model stub at `web/app/graph-prototype/page.tsx`.

- **+ button** (floating, canvas bottom-right) opens a chooser for the 4 components; a **left palette** also lists them. Scanner placement auto-wires from `universe.out`.
- **Generic typed ports** with relaxed ordering: `symbolkey` / `scan_rows` / `filtered_rows` / `enriched_rows` / `report_rows`; assignability via `INPUT_ACCEPTS` (Quant accepts scan+filtered; Search accepts scan/filtered/enriched; Report accepts scan/filtered/enriched on its structural port + optional enriched context). Skip edges legal (Scanner → Report).
- **Settings panels** per component (selection-driven, write `node.data.variables`, grouped + collapsible):
  - Scanner: `family` select (ep_gap/vcp/bo/custom) switches which threshold groups show (EP baseline/strict, VCP, BO, custom scan_id).
  - Quant: every gate/threshold from ticket 01 exposed (liquidity, mcap, stage-2, structural rubric, BO essentials, funnel + Q_base).
  - AI Search: topic/depth/time_range/max_results, taxonomy+leadership query toggles, LLM prompt template.
  - Report: report format, min_rating, down-only caps toggle, hard-cap ceilings.
- **Templates** (localStorage): component template (selected node's type + variables) and graph template (nodes + edges); save + load in the inspector / header.
- **Mark-red**: live edge validation with a red stroke on invalid edges. Dormant in the stub — component port types are fixed, so no variable edit currently breaks a wire; the mechanism activates once custom tools can declare dynamic ports (ticket 13).
- **Lane-merge table** keyed on SymbolKey, fake rows.

Verified: `npx tsc --noEmit` clean, `npm run build` succeeds (route `/graph-prototype` registered, 61.6 kB). `npm test` currently fails across all suites with a pre-existing vitest transform issue ("No test suite found in file" / `vi` undefined) that predates this ticket and is unrelated to the stub — no test imports `graph-prototype`.

To react: run `npm run dev` in `web/` and open `http://localhost:3000/graph-prototype`.
