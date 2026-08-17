"""Preview estimate for a graph run (T22).

Computes a best-effort cost + wall-clock estimate before execution using
placeholder per-operation unit costs, so the editor can show a warning modal
("this run may take ~8 min and ~$1.20"). Estimates are advisory: the walker
never consults them.
"""

from __future__ import annotations

from typing import Any, Optional

from .registry import REGISTRY

# Placeholder per-op costs / durations (override in config if real pricing lands).
OHLCV_PER_SYMBOL_USD = 0.0001   # Polygon OHLCV fetch
RESOLVE_PER_SYMBOL_USD = 0.00005
LLM_CALL_USD = 0.02             # one enrichment LLM parse (+ 2 Tavily searches)
FETCH_SECONDS_PER_SYMBOL = 0.06  # OHLCV + resolution wall time per symbol
LLM_SECONDS_PER_SYMBOL = 4.0     # dual Tavily + LLM parse per enriched symbol
SECONDS_PER_SYMBOL_COST = {      # rough: data-heavy scanners, slow enrich
    "scanner": 0.05,
    "quant": 0.001,
    "search": 4.0,
    "report": 0.001,
}


def estimate_graph_run(
    definition: dict[str, Any],
    symbol_count: int,
    tools: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Estimate cost/duration for ``definition`` over ``symbol_count`` symbols."""
    tools = tools or REGISTRY
    nodes = definition.get("nodes") or []

    total_cost = symbol_count * RESOLVE_PER_SYMBOL_USD
    total_seconds = symbol_count * FETCH_SECONDS_PER_SYMBOL

    node_estimates: list[dict[str, Any]] = []
    for node in nodes:
        spec = tools.get(node.get("tool_id"))
        if spec is None:
            continue
        secs = SECONDS_PER_SYMBOL_COST.get(spec.id, 0.001) * symbol_count
        cost = 0.0
        if spec.id == "search":
            cost = symbol_count * LLM_CALL_USD
        elif spec.id in ("scanner", "quant"):
            cost = symbol_count * (OHLCV_PER_SYMBOL_USD if spec.id == "scanner" else 0.0)
        total_seconds += secs
        total_cost += cost
        node_estimates.append(
            {"node_id": node.get("id"), "tool_id": spec.id, "seconds": round(secs, 1), "cost": round(cost, 2)}
        )

    warnings: list[str] = []
    if total_seconds > 600:
        warnings.append(f"estimated wall time {_fmt_duration(total_seconds)} exceeds 10 minutes")
    if total_cost > 5.0:
        warnings.append(f"estimated LLM/data cost ${total_cost:.2f} may be significant")

    return {
        "symbols": symbol_count,
        "seconds": round(total_seconds, 1),
        "duration": _fmt_duration(total_seconds),
        "cost": round(total_cost, 2),
        "nodes": node_estimates,
        "warnings": warnings,
    }


def estimate_symbol_count(
    universe: dict[str, Any],
    force_symbols: str = "",
) -> int:
    """Advisory symbol count: paste list length or a nominal sweep size."""
    if universe.get("source") == "snapshot":
        return 3000  # prefiltered sweep universe (placeholder)
    lines = [ln for ln in force_symbols.replace(",", "\n").splitlines() if ln.strip()]
    return max(1, len(lines))


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}m"


__all__ = ["estimate_graph_run", "estimate_symbol_count"]
