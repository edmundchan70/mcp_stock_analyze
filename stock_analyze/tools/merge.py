"""Row identity + merge-table normalization (T11/T19).

Rows flow between components keyed by SymbolKey ``(symbol, exchange)``.
Auto-merge at a junction dedupes by key (first occurrence wins). The
Lane-Merge Table is the final report output: one row per symbol, with the
``lanes`` column naming every report node that surfaced it.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

SymbolKey = tuple[str, str]


def symbol_key(row: dict[str, Any]) -> SymbolKey:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("exchange") or "NASDAQ").upper(),
    )


def merge_rows(
    *groups: Iterable[dict[str, Any]],
    keep: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    """Auto-merge row groups keyed by SymbolKey; first occurrence wins.

    ``keep`` optionally picks the winner when a key appears twice (e.g.
    ``lambda r: r.get("rating", 0)`` for highest-rating dedupe).
    """
    merged: dict[SymbolKey, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            key = symbol_key(row)
            if key not in merged:
                merged[key] = dict(row)
                continue
            if keep is not None and keep(row) > keep(merged[key]):
                merged[key] = dict(row)
    return list(merged.values())


def to_merge_table(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Normalize report rows into a Lane-Merge Table payload.

    Columns are the union of row keys (minus ``lanes``), plus ``symbol``,
    ``exchange``, ``rating`` and ``lanes`` (pipe-joined lane labels —
    the scanner family that produced the symbol, or the report node id).
    """
    rows = list(rows)
    seen: dict[SymbolKey, dict[str, Any]] = {}
    for row in rows:
        key = symbol_key(row)
        lane = row.get("_lane") or row.get("_source")
        lanes = {str(lane)} if lane else set()
        if key in seen:
            seen[key]["lanes"] = _join_lanes(seen[key].get("lanes"), lanes)
            seen[key]["rating"] = max(
                float(seen[key].get("rating") or 0), float(row.get("rating") or 0)
            )
            continue
        item = {k: v for k, v in row.items() if k not in ("_source", "_lane")}
        item["lanes"] = " | ".join(sorted(lanes))
        seen[key] = item

    final = list(seen.values())
    final.sort(key=lambda r: (float(r.get("rating") or 0), r.get("symbol", "")), reverse=True)

    columns: list[str] = ["symbol", "exchange", "rating", "lanes"]
    for row in final:
        for k in row:
            if k not in columns:
                columns.append(k)
    # keep primary columns first, then the union extras
    columns = [c for c in columns if c in ("symbol", "exchange", "rating", "lanes")]
    extra = []
    for row in final:
        for k in row:
            if k not in columns and k not in extra:
                extra.append(k)
    columns.extend(extra)

    return {
        "columns": columns,
        "rows": final,
        "count": len(final),
    }


def _join_lanes(existing: Any, lanes: set[str]) -> str:
    cur = set(str(existing).split(" | ")) if existing else set()
    cur |= lanes
    return " | ".join(sorted(c for c in cur if c))


__all__ = [
    "SymbolKey",
    "merge_rows",
    "symbol_key",
    "to_merge_table",
]
