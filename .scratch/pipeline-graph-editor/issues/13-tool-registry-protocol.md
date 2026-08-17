Type: grilling
Status: open

## Question

Define the user-tool protocol that generalizes ticket 06's Custom Scan registry to all 4 component types. Decide:
- `ToolSpec` shape: id, name, phase (1–4), input ports, output ports, params schema, and callable `(inputs, params) -> rows`.
- Registration mechanism (`@register("id")` in `stock_analyze/custom_scans/` — or a new package?), startup validation, and how registered tools surface as per-entry palette items.
- Whether a registered tool can declare custom port types (which would activate the mark-red edge validation in ticket 10), or only the 5 canonical row stages.

Blocked by: 11.
