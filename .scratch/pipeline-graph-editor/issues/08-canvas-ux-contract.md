> **SUPERSEDED — re-scoped.** The canvas UX contract ideas (typed handles, root `isValidConnection`, selection-driven inspector, tabbed results) survive unchanged; family-specific node/port details are superseded by the component model (ticket 10 + tickets 12–17).

Type: grilling
Status: resolved

## Question

Write the canvas UX contract: the n8n/Railway-feel interaction spec for drag-drop wiring, typed-port feedback, inline variable inspector, and the lane-merge results table. Depends on the UX research (03) and the throwaway canvas stub (09).

## Answer

### Wiring

- Phases are React Flow nodes; Ports are **typed handles** (`source`/`target`) whose `id` is the Port name (e.g. `bucket`, `context`, `structural`).
- A wire is created by dragging from a source handle to a target handle (React Flow default). `connectOnClick` stays on for accessibility.
- One root `isValidConnection` reads `sourceHandle`/`targetHandle` port types against the node/port matrix (ticket 07). Incompatible types → return `false` (edge not created); target handle gets `connecting`/`valid` CSS classes to red-highlight and snap-back.
- Role ordering (1→2→3) and family match are enforced by the same validity check; cycles are impossible (DAG).

### Inspector

- Click (or double-click) a Phase to open a selection-driven side `Panel`.
- The inspector renders declaratively-typed fields for that Phase's `variables` (from ticket 01 inventory): number/boolean/select/text. Edits write straight back into `node.data.variables` (single source of truth).
- Optional ports show as toggleable/empty inputs; leaving them unconnected is valid.

### Results

- Each Phase's output is previewable in a tabbed Table / JSON / Schema panel (n8n INPUT/OUTPUT model).
- The final view is a **lane-merge table** keyed on `SymbolKey`: one row per symbol, with family/source tag and a generic rating/score if present; duplicate symbols across lanes are collapsed.
