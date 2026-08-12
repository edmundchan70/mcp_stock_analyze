"""TradingView screener adapter for US-listed EP universe discovery."""

from __future__ import annotations

import logging
import time
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
    "AvgValue.Traded_60d",
    "Value.Traded",
    "exchange",
]

# Columns used for VCP Agent 1 screener pre-filter (TradingView field names).
VCP_COLUMNS = [
    "name",
    "close",
    "SMA50",
    "SMA200",
    "volume",
    "average_volume_60d_calc",
    "market_cap_basic",
    "description",
    "exchange",
    "type",
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


def fetch_us_vcp_universe(
    *,
    min_price: float = 10.0,
    min_adv: float | None = None,
    min_mktcap: float = 100_000_000,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """Pull US equities from TradingView screener with Stage 2 pre-filters.

    Filters at source: close >= $10, close > SMA50, close > SMA200,
    ADV >= $10M (shared MIN_ADV_DOLLAR), mktcap >= $100M, type=stock, america market.
    Sorted by volume descending.
    """
    from tradingview_screener import Query, col
    from stock_analyze.scanners.vcp.gates import MIN_ADV_DOLLAR

    if min_adv is None:
        min_adv = MIN_ADV_DOLLAR

    query = (
        Query()
        .select(*VCP_COLUMNS)
        .where(
            col("close") >= min_price,
            col("close") > col("SMA50"),
            col("close") > col("SMA200"),
            col("average_volume_60d_calc").multiply(col("close")) >= min_adv,
            col("market_cap_basic") >= min_mktcap,
            col("type").isin(["stock"]),
        )
        .order_by("volume", ascending=False)
        .limit(limit)
    )
    if hasattr(query, "set_markets"):
        query = query.set_markets("america")

    count, df = query.get_scanner_data()
    logger.info(
        "VCP screener returned %s rows (reported count=%s)",
        len(df) if df is not None else 0,
        count,
    )
    return [r for r in dataframe_to_rows(df) if _is_us_listed(r)]


def fetch_us_bo_universe(
    *,
    min_price: float = 10.0,
    min_adv: float | None = None,
    min_mktcap: float = 100_000_000,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """Pull US equities from TradingView screener with Qullamaggie pre-filters.

    Qullamaggie names must already be in a Stage 2 uptrend with liquid enough
    dollar volume for a breakaway gap. Filters at source: close >= $10,
    close > SMA50, close > SMA200, ADV >= $10M, mktcap >= $100M, america market.
    Sorted by volume descending.
    """
    from tradingview_screener import Query, col
    from stock_analyze.scanners.vcp.gates import MIN_ADV_DOLLAR

    if min_adv is None:
        min_adv = MIN_ADV_DOLLAR

    query = (
        Query()
        .select(*VCP_COLUMNS)
        .where(
            col("close") >= min_price,
            col("close") > col("SMA50"),
            col("close") > col("SMA200"),
            col("average_volume_60d_calc").multiply(col("close")) >= min_adv,
            col("market_cap_basic") >= min_mktcap,
            col("type").isin(["stock"]),
        )
        .order_by("volume", ascending=False)
        .limit(limit)
    )
    if hasattr(query, "set_markets"):
        query = query.set_markets("america")

    count, df = query.get_scanner_data()
    logger.info(
        "BO screener returned %s rows (reported count=%s)",
        len(df) if df is not None else 0,
        count,
    )
    return [r for r in dataframe_to_rows(df) if _is_us_listed(r)]


def fetch_symbols(
    symbols: Sequence[tuple[str, str]],
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Fetch screener rows by bare symbol name across the america market.

    Matches pasted tickers by name only (no exchange prefix) so the screener
    resolves the true exchange for symbols listed on NYSE, AMEX, etc. that the
    LLM may have defaulted to NASDAQ.
    """
    if not symbols:
        return []
    from tradingview_screener import Query, col

    names = sorted({sym.strip().upper() for sym, _ in symbols if sym and sym.strip()})
    if not names:
        return []
    limit = max(limit, len(names))
    query = (
        Query()
        .select(*EP_COLUMNS)
        .where(col("name").isin(names))
        .set_markets("america")
        .limit(limit)
    )
    logger.info("Fetching %d force symbols from TradingView screener...", len(names))
    t0 = time.perf_counter()
    _, df = query.get_scanner_data()
    elapsed_s = time.perf_counter() - t0
    rows = dataframe_to_rows(df)
    logger.info("Screener returned %d rows for force symbols — %.1fs", len(rows), elapsed_s)
    return rows


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
