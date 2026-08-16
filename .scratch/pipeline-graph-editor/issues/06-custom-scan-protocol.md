> **SUPERSEDED — re-scoped.** The `@register("id")` registry idea survives and is *generalized*: from scan-only to all 4 component types (ticket 13). The scan-specific protocol below is the base case.

Type: grilling
Status: resolved

## Question

What is the exact Python protocol for a Custom Scan? A user-authored Role 1 Phase behind a known Scan Port: Universe in, a set of `SymbolKey` plus opaque JSON out. Decide the registration mechanism (by id), the function signature/return type, and how the server discovers and validates a registered Custom Scan before it can be placed on the canvas.

## Answer

Custom Scan uses an **in-repo registry with a decorator**. (Depends on ticket 02 — the Universe Port emits `list[SymbolKey]`.)

### Location and registry

- New package `stock_analyze/custom_scans/__init__.py` exposes:
  - `REGISTRY: dict[str, CustomScanSpec]`
  - `@register(scan_id: str)` decorator that stores the function under `scan_id`
  - `get_registered_scans() -> list[str]`
- A `CustomScanSpec` is the callable plus a small metadata record (id, name, description).

### Protocol

- Signature: `Callable[[list[SymbolKey], dict[str, Any]], list[dict]]`
  - Arg 1: the Universe `list[SymbolKey]` (`(symbol, exchange)` tuples).
  - Arg 2: the node's inspector `variables` (params).
  - Return: a list of rows, each a dict with at minimum `{"symbol": str, "exchange": str}` plus any opaque extra keys (the "opaque JSON").
- Custom Scan is **scan-only**: it never enters a family's Role 2/3. It merges by lane at the end (keyed on `SymbolKey`).

### Discovery and validation

- The server imports `stock_analyze.custom_scans` at startup and validates each registered entry: it asserts the callable accepts 2 positional params and returns an iterable of mappings.
- A Custom Scan node on the canvas carries a `scan_id` variable; the inspector lists ids from `get_registered_scans()`. Placement is rejected if the id is not registered.
