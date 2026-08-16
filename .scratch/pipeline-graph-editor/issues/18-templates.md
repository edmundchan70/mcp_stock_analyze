Type: grilling
Status: open

## Question

Decide template storage: **component template** (a component's type + variables) vs **graph template** (nodes + edges + positions + variables). Decide:
- Postgres tables: does the `graph` JSON shape from ticket 07 change for the component model (node `type` = component id, edges unchanged)? New `component_templates` table alongside `pipeline_definitions`?
- Save/load API endpoints for both template kinds; how Universe stays per-Run / per-graph.
- Where templates surface in the UI: palette (component templates as quick-add), inspector (save/apply), header (graph save/load).

Blocked by: 11.
