# Component Graph Editor — Spec Map

## Destination

A handoff-ready spec + throwaway UI for a **component-based pipeline graph editor**: a **+ button** adds one of 4 configurable components — Scanner, Quant Filter/Gate, AI Search, Report — each with a full settings panel (TradingView-screener style for Scanner, all gates/thresholds editable for Quant, full search settings for AI Search, report/caps fields for Report). Both individual components and whole graphs are saveable as **templates**. The stub at `web/app/graph-prototype` is the UI language to react to.

## Notes

- Domain: the `stock_analyze` scan pipelines (EP / VCP / BO) under `mcp_stock_analyze/`.
- Skills every session should consult: `/grilling`, `/domain-modeling`, `frontend-design`, `sass-uiux-redesign`.
- Tracker: local markdown (`.scratch/pipeline-graph-editor/`).
- **Re-scope**: this effort supersedes the earlier family-specific node model (EP Scan / VCP Enrich nodes, enforced Roles 1–3). `spec.md` and tickets 02/04/05/06/08 are re-labeled as superseded; their facts survive as research inputs for new tickets.
- Destination is a spec, not the production build. Prototype tickets produce throwaway artifacts to react to.
- Already-settled decisions (gist only — detail lives in the grilling history and ticket 10):
  - 4 generic components: **Scanner** (technical screening), **Quant Filter/Gate** (all gates/thresholds editable), **AI Search** (LLM/Tavily search settings), **Report** (LLM report generation).
  - **Universe** is auto-seeded once as the start node, not in the palette; new Scanners auto-wire from `universe.out`.
  - Add flow: left palette + a floating **+ button** chooser.
  - Wiring legality = **port-type assignability only** (relaxed role ordering; skip edges legal, e.g. Scanner → Report).
  - Data between tools = **rows keyed by SymbolKey**; same-type inputs **auto-merge** by symbol before a tool runs; the merge table falls out naturally.
  - Per-component settings panels are selection-driven and write `node.data.variables`.
  - **Templates**: a component's config saves as a **component template**; any graph saves as a **graph template**. Storage decision still open (ticket 18).
  - Registered custom tools appear as **per-entry palette items** (generalizes ticket 06's Custom Scan registry to all 4 components).
  - Param changes that break wires **mark the edge red** but keep it (dormant in the stub: component port types are fixed; activates once custom tools can declare dynamic ports).

## Decisions so far

<!-- the index — one line per closed ticket -->

- [Inventory Phase inspector tunables](issues/01-inventory-phase-inspector-tunables.md) — full list of every gate/threshold/cap/profile + RunConfig field with `file:line`, grouped by owning Phase. Still the canonical tunables list (feeds tickets 14/15/17).
- [Graph-editor UX sources](issues/03-graph-editor-ux-sources.md) — n8n/Railway/React Flow interaction patterns with citations. Still canonical for the canvas UX.
- [Definition JSON + API](issues/07-definition-json-save-load-api.md) — `pipeline_definitions` table, `runs.definition_id`/`graph_snapshot`, `/api/definitions`. Partially superseded: the `graph` JSON shape survives; endpoint list reused; the family-specific taxonomy and `pipeline_type` coupling re-open in ticket 18.
- [Throwaway canvas stub](issues/09-throwaway-canvas-stub.md) — original family-specific stub. Superseded as the UI language by [the component stub](issues/10-add-component-palette.md), but the verified-build details remain useful.
- [Add-component palette stub](issues/10-add-component-palette.md) — component-model throwaway stub: + button, 4 components, settings panels, template save, SymbolKey merge.

## Frontier (open tickets)

- [Tool data model](issues/11-tool-data-model.md) — what flows between components; port labels; auto-merge semantics. Blocks 13, 18.
- [Component taxonomy](issues/12-component-taxonomy.md) — the 4 components, their roles, what config each owns; how EP/VCP/BO/Custom families map onto the Scanner component. Blocks 14–17.
- [Tool registry protocol](issues/13-tool-registry-protocol.md) — ToolSpec (id, name, phase, ports, params schema, callable); generalizes ticket 06.
- [Scanner config surface](issues/14-scanner-config-surface.md) — TradingView-screener-style Scanner config (research).
- [Quant config surface](issues/15-quant-config-surface.md) — all gates/thresholds from ticket 01 exposed as editable (research).
- [Search config surface](issues/16-search-config-surface.md) — Tavily search settings surface (research).
- [Report config surface](issues/17-report-config-surface.md) — report fields/caps surface (research).
- [Templates](issues/18-templates.md) — component vs graph template; storage + save/load API (grilling).

## Not yet specified

- Server-side execution of a component graph against today's `run_daily` (the old "DAG walker"); shape superseded pending tickets 11–13.
- Whether the CLI/wizard loads component graphs.
- Per-component inspector layout details (graduates after tickets 12–17).

## Out of scope

- Building the production editor.
- The old family-specific node taxonomy (EP Scan / VCP Enrich as distinct node types); gate-as-nodes; cycles; in-browser code nodes; multi-user auth; Adapter phases.
