"""Premarket grep Agent 1 runner — snapshot rows → change% filter → cap → tier."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from stock_analyze.models.premarket import PremarketScanBucket, PremarketStock
from stock_analyze.scanners.premarket.metrics import strength_tier, volume_flag

logger = logging.getLogger(__name__)


def select_premarket_candidates(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_change_pct: float,
    cap: int,
    apply_gates: bool = True,
) -> list[dict[str, Any]]:
    """Snapshot rows → change%-filter → sort desc → cap (no enrichment).

    Shared by the pipeline (to bound detail/ADV resolution) and the runner
    (authoritative survivor list).
    """
    candidates = [
        dict(r)
        for r in rows
        if r.get("change_pct") is not None
        and (not apply_gates or float(r["change_pct"]) >= min_change_pct)
    ]
    candidates.sort(key=lambda r: float(r["change_pct"]), reverse=True)
    return candidates[:cap]


def run_premarket_scan(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: Optional[date] = None,
    apply_gates: bool = True,
    min_change_pct: float = 5.0,
    min_vol_mult: float = 0.0,
    cap: int = 300,
    force_set: Optional[set[tuple[str, str]]] = None,
) -> PremarketScanBucket:
    """Filter premarket snapshot rows into a capped, tiered survivor bucket.

    Each input row carries ``symbol``/``exchange`` plus optional ``change_pct``,
    ``price``, ``volume``, ``name``, ``sector`` and ``adv_20d`` (20-day average
    dollar volume). Keep rule: ``change_pct >= min_change_pct``, sorted by
    change_pct desc, capped to ``cap`` survivors. Rows whose (symbol, exchange)
    is in ``force_set`` bypass the change gate (user-pasted). ``apply_gates=False``
    keeps every row (cap still applied).

    The ``volume_flag`` is ``volume >= min_vol_mult × adv_20d``; when
    ``min_vol_mult <= 0`` every survivor's flag is False (feature off).
    """
    day = as_of or datetime.now(timezone.utc).date()
    force = force_set or set()

    stocks: list[PremarketStock] = []
    for row in rows:
        change_pct = row.get("change_pct")
        if change_pct is None:
            change_pct = 0.0
        symbol = str(row.get("symbol") or "").upper()
        exchange = str(row.get("exchange") or "NASDAQ").upper()
        if not symbol:
            continue
        forced = (symbol, exchange) in force or bool(row.get("force"))
        if apply_gates and not forced and float(change_pct) < min_change_pct:
            continue
        stocks.append(
            PremarketStock(
                symbol=symbol,
                exchange=exchange,
                change_pct=float(change_pct),
                price=float(row["price"]) if row.get("price") is not None else None,
                volume=float(row["volume"]) if row.get("volume") is not None else None,
                company_name=str(row.get("name") or ""),
                sector=str(row.get("sector") or "Unknown"),
                adv_20d=float(row["adv_20d"]) if row.get("adv_20d") is not None else None,
                vol_flag=volume_flag(row.get("volume"), row.get("adv_20d"), min_vol_mult),
                strength=strength_tier(float(change_pct)),
                as_of=day,
            )
        )

    stocks.sort(key=lambda s: s.change_pct, reverse=True)
    stocks = stocks[:cap]

    counts = {str(t): sum(1 for s in stocks if s.strength == t) for t in (5, 4, 3, 2)}
    return PremarketScanBucket(
        as_of=datetime.now(timezone.utc),
        universe_source="snapshot",
        gates_applied=apply_gates,
        min_change_pct=min_change_pct,
        ratings=stocks,
        count=len(stocks),
        counts=counts,
    )


__all__ = ["run_premarket_scan", "select_premarket_candidates"]
