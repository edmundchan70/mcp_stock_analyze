"""Normalize TradingView screener rows into EpStock metrics."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from stock_analyze.data.symbols import parse_symbol_exchange


def compute_gap_pct(open_price: float, prior_close: float) -> float:
    if prior_close == 0:
        raise ValueError("prior_close must be non-zero")
    return (open_price - prior_close) / prior_close * 100.0


def _f(row: Mapping[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                continue
    return None


def normalize_row(
    row: Mapping[str, Any],
    *,
    as_of: date,
    force_included: bool = False,
) -> "EpStock":
    from stock_analyze.models.ep import EpStock

    raw_name = str(row.get("name") or row.get("symbol") or "")
    symbol, exchange = parse_symbol_exchange(raw_name, row.get("exchange"))
    if row.get("symbol") and ":" not in str(row.get("name") or ""):
        symbol = str(row["symbol"]).strip().upper()
    if row.get("exchange"):
        exchange = str(row["exchange"]).strip().upper()

    price = _f(row, "close", "price")
    if price is None:
        raise ValueError(f"Missing price/close for {raw_name or symbol}")

    open_price = _f(row, "open")
    prior_close = _f(row, "prior_close")
    gap = None
    if open_price is not None and prior_close is not None:
        gap = compute_gap_pct(open_price, prior_close)
    else:
        gap = _f(row, "gap", "gap_pct")
    if gap is None:
        raise ValueError(f"Missing gap for {symbol}")

    rvol = _f(row, "relative_volume_10d_calc", "rvol10")
    if rvol is None:
        raise ValueError(f"Missing RVOL10 for {symbol}")

    market_cap = _f(row, "market_cap_basic", "market_cap")
    event_dv = _f(row, "Value.Traded", "event_dollar_volume", "value_traded")
    if event_dv is None:
        volume = _f(row, "volume")
        if volume is not None:
            event_dv = price * volume

    # Prefer true average dollar volume fields from TradingView.
    # Nearest bulk field is 60d; domain name remains avg_dollar_volume_50d.
    avg_dollar = _f(
        row,
        "avg_dollar_volume_50d",
        "AvgValue.Traded_60d",
        "AvgValue.Traded_30d",
        "average_volume_dollar_50d",
    )
    if avg_dollar is None:
        avg_vol = _f(
            row,
            "average_volume_60d_calc",
            "average_volume_30d_calc",
            "average_volume_10d_calc",
            "avg_volume_50d",
        )
        if avg_vol is not None:
            avg_dollar = price * avg_vol

    return EpStock(
        symbol=symbol,
        exchange=exchange,
        price=price,
        market_cap=market_cap,
        avg_dollar_volume_50d=avg_dollar,
        gap_pct=gap,
        rvol10=rvol,
        event_dollar_volume=event_dv,
        force_included=force_included,
        as_of=as_of,
    )
