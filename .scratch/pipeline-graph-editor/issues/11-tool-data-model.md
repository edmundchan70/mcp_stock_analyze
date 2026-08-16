Type: grilling
Status: open

## Question

What exactly is the data flowing between components? Settled direction: **rows keyed by SymbolKey** (`symbol` + `exchange` + opaque extra columns), and same-type inputs **auto-merge** by symbol before a tool runs. Decide:
- The canonical port labels per stage (`symbolkey` / `scan_rows` / `filtered_rows` / `enriched_rows` / `report_rows`?).
- Whether a "row" has a canonical minimum shape beyond symbol/exchange.
- Auto-merge semantics at a junction: dedupe by SymbolKey before invoking a tool? What happens to rows that fail a component (soft-fail)?

Blocks: 13, 18.
