> **Superseded as the UI language** by ticket 10 (the component-model stub). The verified-build details below remain useful.

Type: prototype
Status: resolved

## Question

Produce a throwaway canvas stub to react to: a Universe node plus one family chain (e.g. EP Scan → EP Catalyst → EP Rating), drag edges between Phases, select a Phase to open a fake inspector. Cheap and rough — for reaction, not production.

## Answer

Built a working React Flow (v12) prototype at `web/app/graph-prototype/page.tsx`.

- Depends on `@xyflow/react` (added to `web/package.json`).
- Two lanes fanned out from a Universe node: `EP Scan → EP Catalyst → EP Rating` and `VCP Scan → VCP Enrich → VCP Report`.
- Typed handles per Port (from spec.md section 2); a single root `isValidConnection` enforces port-type assignability (`catalyst` → `ep_scan`) and Role ordering (1→2→3); incompatible wires are rejected.
- Click a node to open a side inspector rendering its `variables` (select/number/boolean), writing back to `node.data`.
- A lane-merge table (keyed on `SymbolKey`) shows a fake merged result.
- Matches the existing dark slate theme (no new design system).

Verified: `npx tsc --noEmit` clean, `npm run build` succeeds (route `/graph-prototype` registered), `npm test` 17/17 pass.

To react: run `npm run dev` in `web/` and open `http://localhost:3000/graph-prototype`.
