"""TradingView screener adapter for US-listed EP universe discovery."""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

# Columns used for EP Agent 1 metrics (TradingView field names).
EP_COLUMNS = [
    "name",
    "close",
    "open",
    "gap",
    "volume",
    "relative_volume_10d_calc",
    "market_cap_basic",
    "average_volume_60d_calc",
    "Value.Traded",
    "exchange",
]

# Phase 1: US listed major venues only (exclude OTC / pink sheets).
US_LISTED_EXCHANGES = frozenset(
    {
        "NYSE",
        "NASDAQ",
        "AMEX",
        "NYSE ARCA",
        "NYSEAMERICAN",
        "BATS",
        "CBOE",
        "NYSEARCA",
    }
)


def fetch_us_ep_universe(
    *,
    min_price: float = 1.0,
    min_gap_pct: float = 4.0,
    min_rvol10: float = 1.5,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """
    Pull US equities from TradingView screener with Baseline-level prefilters.

    Uses america market; filters at source so local Strict gates can still run
    on the returned set.
    """
    from tradingview_screener import Query, col

    query = (
        Query()
        .select(*EP_COLUMNS)
        .where(
            col("close") >= min_price,
            col("gap") >= min_gap_pct,
            col("relative_volume_10d_calc") >= min_rvol10,
            col("type").isin(["stock"]),
        )
        .order_by("gap", ascending=False)
        .limit(limit)
    )
    # Default Query markets include america; set explicitly for clarity.
    if hasattr(query, "set_markets"):
        query = query.set_markets("america")

    count, df = query.get_scanner_data()
    logger.info("Screener returned %s rows (reported count=%s)", len(df) if df is not None else 0, count)
    return [r for r in dataframe_to_rows(df) if _is_us_listed(r)]


def fetch_symbols(
    symbols: Sequence[tuple[str, str]],
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Fetch screener rows for specific EXCHANGE:SYMBOL pairs (force includes)."""
    if not symbols:
        return []
    from tradingview_screener import Query

    tickers = [f"{exch.upper()}:{sym.upper()}" for sym, exch in symbols]
    # tradingview-screener accepts set_tickers on some versions
    query = Query().select(*EP_COLUMNS)
    if hasattr(query, "set_tickers"):
        query = query.set_tickers(*tickers)
    elif hasattr(query, "set_symbols"):
        query = query.set_symbols(tickers=tickers)
    else:
        logger.warning("Query has no set_tickers; falling back to empty force fetch")
        return []

    query = query.limit(limit)
    _, df = query.get_scanner_data()
    return dataframe_to_rows(df)


def _is_us_listed(row: dict[str, Any]) -> bool:
    exch = str(row.get("exchange") or "").strip().upper()
    if not exch:
        name = str(row.get("name") or "")
        if ":" in name:
            exch = name.split(":", 1)[0].strip().upper()
    if exch == "OTC" or exch.startswith("OTC"):
        return False
    return exch in US_LISTED_EXCHANGES or exch in {"NYSE", "NASDAQ", "AMEX"}


def dataframe_to_rows(df: Optional[pd.DataFrame]) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    # tradingview-screener often returns 'ticker' as EXCHANGE:SYMBOL and 'name' as bare symbol
    out = df.reset_index()
    records = out.to_dict(orient="records")
    normalized: list[dict[str, Any]] = []
    for rec in records:
        row = {str(k): v for k, v in rec.items() if pd.notna(v)}
        ticker = row.get("ticker") or row.get("symbol")
        bare_name = row.get("name")
        if ticker and ":" in str(ticker):
            row["name"] = str(ticker)
            exch, sym = str(ticker).split(":", 1)
            row.setdefault("exchange", exch)
            row.setdefault("symbol", sym)
        elif bare_name and ":" in str(bare_name):
            row["name"] = str(bare_name)
        elif ticker:
            row["name"] = str(ticker)
        normalized.append(row)
    return normalized
