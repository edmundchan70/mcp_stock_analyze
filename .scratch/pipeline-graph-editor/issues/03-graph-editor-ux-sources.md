Type: research
Status: resolved

## Question

Extract, from primary sources, the interaction patterns the canvas UX contract must specify: node/edge drag-drop, typed-port compatibility feedback, inline per-node variable inspector, and a lane/merge results table. Cover n8n, Railway's deploy graph, and React Flow (the likely implementation library). Cite each pattern to its source doc/URL.

## Answer

### n8n (`docs.n8n.io`)

- **Connection**: drag from a node's output connector to the target's input connector; delete via hover + Delete. `https://docs.n8n.io/build/understand-workflows/workflow-components/connect-nodes-together.md`
- **Canvas / node panel**: empty workflow shows "Add first step"; "Add node" opens a searchable nodes panel. `https://docs.n8n.io/build/understand-workflows/workflow-components/work-with-nodes.md`
- **Compatibility is structural, not typed**: no colored/disabled ports; feedback is error routing (On Error → Continue, Retry On Fail). `https://docs.n8n.io/build/understand-workflows/workflow-components/work-with-nodes.md`
- **Inspector (Node Details View)**: double-click a node opens NDV with Parameters / Settings / Docs tabs + Input/Output data panels. `https://docs.n8n.io/build/work-with-data/pin-and-mock-data.md`
- **Declaratively typed parameters** (string/number/boolean/select/code) with parameter hints and `info`/`warning`/`danger` node hints. `https://docs.n8n.io/connect/create-nodes/build-your-node/reference/node-ui-elements.md`
- **Drag-to-map**: drag a field from INPUT into a parameter to auto-generate an expression. `https://docs.n8n.io/build/work-with-data/understand-n8ns-data-structure.md`
- **Data tables**: INPUT panel renders items as a table; OUTPUT has JSON vs table + Pin data; Data tables tab is a visual table editor. `https://docs.n8n.io/build/work-with-data/data-tables.md`

### Railway (`docs.railway.com`)

- **Project Canvas** is the default view; services are spatial tiles; click opens config; New button / `Cmd/Ctrl+K` command palette creates services. `https://docs.railway.com/projects`, `https://docs.railway.com/services`
- **Edges are derived from references**, not hand-drawn: referencing `${{SERVICE.VAR}}` draws a dashed dependency line; sealing a reference removes it. `https://docs.railway.com/variables`
- **Deploy ordering from the reference chain**; circular references are broken and deployed in parallel. `https://docs.railway.com/deployments/deployment-actions`
- **Variables tab** (form fields or RAW editor) with staged changes and reference autocomplete. `https://docs.railway.com/variables`
- **Inspector = Settings tab** on the service tile (Source, Networking, build/start), with Metrics/Deployments siblings. `https://docs.railway.com/services`

### React Flow (`reactflow.dev` / `@xyflow/react`)

- **Handles are the ports**: `type: source|target`, `position`, unique `id` referenced by edges via `sourceHandle`/`targetHandle`. `https://reactflow.dev/learn/customization/handles`
- **Connection gesture**: drag handle-to-handle; placeholder "connection line" while dragging; `connectOnClick` enables click-source-then-click-target; `connectionDragThreshold` prevents accidental edges. `https://reactflow.dev/learn/concepts/terms-and-definitions`
- **Completion**: `onConnect` → `addEdge`; `onConnectStart`/`onConnectEnd` bracket the gesture; `onConnectEnd` fires even on invalid drops (exposes `connectionState`). `https://reactflow.dev/examples/interaction/validation`
- **Typed-port rejection**: `isValidConnection(connection) => boolean` returning `false` prevents the edge; recommended on `<ReactFlow>` root. `https://reactflow.dev/api-reference/types/is-valid-connection`
- **Connection modes**: `'strict'` (source→target only) vs `'loose'` (allows source-to-source). `https://reactflow.dev/api-reference/react-flow`
- **Visual feedback hooks**: target handle receives `connecting` and `valid` CSS classes during drag — the documented hook for highlight/snap-back. `https://reactflow.dev/learn/customization/handles`
- **Inspector**: drive a `Panel` (or side component) from `onNodeClick`/`onSelectionChange`, writing back via `setNodes`; custom nodes are plain React components; interactive elements get `nodrag`. `https://reactflow.dev/api-reference/components/panel`, `https://reactflow.dev/learn/customization/custom-nodes`
- **Edges**: custom edge types + path helpers (`getBezierPath`, `getSmoothStepPath`, …); `edgesReconnectable` + `onReconnect`. `https://reactflow.dev/learn/customization/custom-edges`

### Implications for our canvas contract

1. **Typed ports = typed handles**: model each Phase's inputs/outputs as React Flow handles with typed `id`s; gate compatibility with a single root `isValidConnection` reading `sourceHandle`/`targetHandle` types; return `false` to reject and use `connecting`/`valid` classes for red-highlight/snap-back.
2. **Inspector = selection-driven side panel writing to `node.data`**: mirror n8n's NDV — open a `Panel` on node click, render declaratively-typed fields, persist edits into `node.data` (single source of truth).
3. **Edges carry a type/dependency contract, not just a line**: adopt Railway's "edges derived from references" idea — an edge's validity encodes a type contract; reject incompatible connections rather than allow a broken graph.
4. **Data preview = tabbed Table/JSON/Schema**: adopt n8n's INPUT/OUTPUT panels with Table/JSON/Schema toggles + pin-to-test, so results are inspectable in one place.
