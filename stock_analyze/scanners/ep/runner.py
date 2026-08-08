"""EP Agent 1: merge universe → normalize → dual Baseline/Strict JSON."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence, Set

from stock_analyze.data.symbols import SymbolKey, row_symbol_key
from stock_analyze.models.ep import EpScanResult, EpStock, StockBucket
from stock_analyze.scanners.ep.gates import BASELINE, STRICT, passes_baseline, passes_strict
from stock_analyze.scanners.ep.metrics import normalize_row

ForceKey = SymbolKey


def run_ep_scan(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: Optional[date] = None,
    force_symbols: Optional[Set[ForceKey]] = None,
    universe_source: Literal["screener", "csv", "hybrid"] = "screener",
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


def load_force_csv(path: str) -> list[ForceKey]:
    """Load force-include CSV with columns symbol,exchange (header required)."""
    import csv
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError("Force-include CSV must have a header row")
    fields = {f.strip().lower(): f for f in reader.fieldnames}
    if "symbol" not in fields:
        raise ValueError("Force-include CSV must include a 'symbol' column")
    sym_key = fields["symbol"]
    exch_key = fields.get("exchange")
    out: list[ForceKey] = []
    for row in reader:
        symbol = (row.get(sym_key) or "").strip().upper()
        if not symbol:
            continue
        exchange = (row.get(exch_key) or "NASDAQ").strip().upper() if exch_key else "NASDAQ"
        out.append((symbol, exchange))
    return out


def merge_force_rows(
    screener_rows: Iterable[Mapping[str, Any]],
    force_keys: Sequence[ForceKey],
    force_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Set[ForceKey], Literal["screener", "csv", "hybrid"]]:
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
        source: Literal["screener", "csv", "hybrid"] = "hybrid"
    elif force_set:
        source = "csv"
    else:
        source = "screener"

    return list(by_key.values()), force_set, source
