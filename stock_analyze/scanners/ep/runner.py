"""EP Agent 1: merge universe → normalize → dual Baseline/Strict JSON."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence, Set

from stock_analyze.data.symbols import SymbolKey, row_symbol_key
from stock_analyze.models.ep import EpScanResult, EpStock, StockBucket
from stock_analyze.scanners.ep.gates import BASELINE, STRICT, passes_baseline, passes_strict
from stock_analyze.scanners.ep.metrics import normalize_row

ForceKey = SymbolKey
UniverseSource = Literal["screener", "force", "hybrid"]


def run_ep_scan(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: Optional[date] = None,
    force_symbols: Optional[Set[ForceKey]] = None,
    universe_source: UniverseSource = "screener",
) -> EpScanResult:
    """Filter normalized rows into baseline and strict buckets."""
    day = as_of or datetime.now(timezone.utc).date()
    force = force_symbols or set()
    force_upper = {(s.upper(), e.upper()) for s, e in force}

    stocks: list[EpStock] = []
    for row in rows:
        try:
            stock = normalize_row(row, as_of=day, force_included=False)
        except (ValueError, TypeError):
            continue
        key = (stock.symbol.upper(), stock.exchange.upper())
        if key in force_upper:
            stock = stock.model_copy(update={"force_included": True})
        stocks.append(stock)

    baseline_stocks = [s for s in stocks if passes_baseline(s)]
    strict_stocks = [s for s in stocks if passes_strict(s)]

    return EpScanResult(
        as_of=datetime.now(timezone.utc),
        universe_source=universe_source,
        session="rth",
        gates={"baseline": BASELINE, "strict": STRICT},
        baseline=StockBucket(count=len(baseline_stocks), stocks=baseline_stocks),
        strict=StockBucket(count=len(strict_stocks), stocks=strict_stocks),
    )


def merge_force_rows(
    screener_rows: Iterable[Mapping[str, Any]],
    force_keys: Sequence[ForceKey],
    force_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Set[ForceKey], UniverseSource]:
    """Merge screener + force-include rows; prefer screener row when duplicate."""
    by_key: dict[ForceKey, dict[str, Any]] = {}
    screener_count = 0
    for row in screener_rows:
        screener_count += 1
        by_key[row_symbol_key(row)] = dict(row)

    for row in force_rows:
        key = row_symbol_key(row)
        if key not in by_key:
            by_key[key] = dict(row)

    force_set = {(s.upper(), e.upper()) for s, e in force_keys}
    if screener_count and force_set:
        source: UniverseSource = "hybrid"
    elif force_set:
        source = "force"
    else:
        source = "screener"

    return list(by_key.values()), force_set, source
