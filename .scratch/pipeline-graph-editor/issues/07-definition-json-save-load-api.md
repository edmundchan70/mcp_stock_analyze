Type: grilling
Status: resolved

## Question

What is the exact shape of a stored Pipeline Definition, and what are the save/load API endpoints? Decide: the JSON schema for nodes/edges/inspector variables; the Postgres tables (definition vs run snapshot); and the REST endpoints. Universe stays per-Run.

## Answer

### Port type map (from ticket 02)

| Type | Meaning |
|---|---|
| `symbolkey` | `list[SymbolKey]` |
| `ep_scan` | `StockBucket` |
| `catalyst` | `CatalystBucket` |
| `ep_rated` | `RatedBucket` |
| `vcp_scan` | `VcpScanBucket` |
| `bo_scan` | `BoScanBucket` |
| `context` | `VcpContextEnrichment` list (shared VCP/BO) |
| `vcp_rated` | `VcpRatedBucket` |
| `bo_rated` | `BoRatedBucket` |
| `custom_scan` | `list[{symbol, exchange, ...opaque}]` |

Assignability rule: `catalyst` is assignable to `ep_scan` (EP Rating reads the structural fields carried through Catalyst), so an `ep_rating` `structural` port accepts either `ep_scan` or `catalyst`. All other types match exactly.

### Node / port matrix

| Node type | Role | Input Port(s) | Output Port |
|---|---|---|---|
| `universe` | start | — | `out` (`symbolkey`) |
| `ep_scan` | 1 | `universe` (`symbolkey`, required) | `bucket` (`ep_scan`) |
| `ep_catalyst` | 2 | `scan` (`ep_scan`, required) | `enriched` (`catalyst`) |
| `ep_rating` | 3 | `structural` (`ep_scan`, required; accepts `catalyst`) | `rated` (`ep_rated`) |
| `vcp_scan` | 1 | `universe` (`symbolkey`, required) | `bucket` (`vcp_scan`) |
| `vcp_enrich` | 2 | `scan` (`vcp_scan`, required) | `enriched` (`context`) |
| `vcp_report` | 3 | `structural` (`vcp_scan`, required) + `context` (`context`, optional) | `rated` (`vcp_rated`) |
| `bo_scan` | 1 | `universe` (`symbolkey`, required) | `bucket` (`bo_scan`) |
| `bo_enrich` | 2 | `scan` (`bo_scan`, required) | `enriched` (`context`) |
| `bo_report` | 3 | `structural` (`bo_scan`, required) + `context` (`context`, optional) | `rated` (`bo_rated`) |
| `custom_scan` | 1 | `universe` (`symbolkey`, required) | `bucket` (`custom_scan`) |

### Definition JSON (Postgres JSONB)

```jsonc
{
  "id": "uuid",
  "name": "EP + VCP dual lane",
  "nodes": [
    { "id": "n0", "type": "universe", "position": { "x": 0, "y": 0 }, "variables": {} },
    { "id": "n1", "type": "ep_scan", "position": { "x": 240, "y": -120 }, "variables": { "select": "strict", "limit": 300, "apply_gates": true } },
    { "id": "n2", "type": "ep_catalyst", "position": { "x": 480, "y": -120 }, "variables": { "max_results": 3 } },
    { "id": "n3", "type": "ep_rating", "position": { "x": 720, "y": -120 }, "variables": { "min_rating": 4 } }
  ],
  "edges": [
    { "id": "e1", "source": "n0", "sourceHandle": "out", "target": "n1", "targetHandle": "universe" },
    { "id": "e2", "source": "n1", "sourceHandle": "bucket", "target": "n2", "targetHandle": "scan" },
    { "id": "e3", "source": "n2", "sourceHandle": "enriched", "target": "n3", "targetHandle": "structural" }
  ]
}
```

### Storage

- New table `pipeline_definitions(id uuid pk, name text not null, graph jsonb not null, created_at timestamptz default now(), updated_at timestamptz default now())`.
- `runs` gains `definition_id uuid null references pipeline_definitions(id) on delete set null` and `graph_snapshot jsonb null`.
- On `POST /api/runs` with a `definition_id`, the server freezes the current `graph` into `graph_snapshot`. Universe (paste/sweep/Force Include) is per-Run and never stored in the Definition.

### Endpoints

- `GET /api/definitions` → list
- `POST /api/definitions` → create `{name, graph}`
- `GET /api/definitions/{id}` → detail
- `PUT /api/definitions/{id}` → update graph
- `DELETE /api/definitions/{id}`
- `POST /api/runs` accepts `definition_id` (optional); existing `pipeline_type`/`force_symbols`/`use_screener` remain for the legacy path.
