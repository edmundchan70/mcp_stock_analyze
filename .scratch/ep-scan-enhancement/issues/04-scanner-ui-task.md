# Ticket 04 — Scanner UI redesign + K/M/B formatting (task)

## Deliverable

1. `web/lib/format.ts` (new) — `fmtCompact(value): string` — global K/M/B compacting (e.g. `1_250_000` → `1.25M`, `123_456_000` → `123.46M`, negatives handled). Replaces `formatCell` in `web/components/MergeTable.tsx` and the ad-hoc `fmtNum`/`fmtUsd` in `web/lib/flow.ts` / `ResultsTable.tsx`.

2. `web/components/flow/filters.tsx` (new) — filter-rail primitives:
   - `Switch` (toggle, `sm` + `md` sizes), `Section` (collapsible rail section with header + master toggle slot), `FilterRow` (label + inline threshold edit), `ThresholdInput` (numeric input with unit suffix), `chips` (active-filter chips).
   - Styled to `web/tailwind.config.ts` / `globals.css` tokens.

3. `web/components/flow/ScannerPhase.tsx`
   - New **EP Technical Test** section in the Scanner filter rail: master toggle (ON by default when `scannerVars.ep_features_enabled`), 5 per-feature toggles + inline threshold edits bound to `scannerVars`.
   - Relocate the run button to the phase header.
   - Results become a **dense, sortable table**: sortable feature columns (click header to sort, up/down), filter-rail toggles, every numeric cell rendered via `fmtCompact`.

4. `web/lib/flow.ts` — `FlowState.scannerVars` already holds the raw vars; add `setScannerVar` action if missing. `rowExplanation` extended with the feature-hold explanation lines.

5. `web/lib/graph.ts` — `scannerGroups("ep")` includes `ep_technical`.

## Verification

- `web/__tests__/flow.test.ts` — reducer actions for the new toggles; `fmtCompact` table tests.
- `web/__tests__/api.test.ts` — scanner payload includes the new vars.
- Lint clean (`npx tsc --noEmit`, eslint).
