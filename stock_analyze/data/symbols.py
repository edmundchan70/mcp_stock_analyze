"""Shared EXCHANGE:SYMBOL parsing."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

SymbolKey = Tuple[str, str]


def parse_symbol_exchange(
    name: str,
    exchange_hint: Optional[str] = None,
) -> SymbolKey:
    """Parse TradingView-style 'EXCHANGE:SYMBOL' or bare symbol."""
    if ":" in name:
        exch, sym = name.split(":", 1)
        return sym.strip().upper(), (exchange_hint or exch).strip().upper()
    return name.strip().upper(), (exchange_hint or "NASDAQ").strip().upper()


def row_symbol_key(row: Mapping[str, Any]) -> SymbolKey:
    name = str(row.get("name") or "")
    if ":" in name:
        return parse_symbol_exchange(name, row.get("exchange"))
    symbol = str(row.get("symbol") or name).strip().upper()
    exchange = str(row.get("exchange") or "NASDAQ").strip().upper()
    return symbol, exchange
