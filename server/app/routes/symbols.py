"""Symbols API: batch OHLCV endpoint for pattern-phase chart evidence."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class OhlcvSymbol(BaseModel):
    """One symbol to fetch (exchange is accepted for parity with SymbolKey)."""

    symbol: str = Field(min_length=1, max_length=16)
    exchange: str = "NASDAQ"


class OhlcvRequest(BaseModel):
    """Body for POST /api/ohlcv."""

    symbols: list[OhlcvSymbol] = Field(min_length=1, max_length=500)
    bars: int = Field(default=300, ge=30, le=500)


@router.post("/ohlcv")
async def ohlcv_batch(body: OhlcvRequest) -> dict[str, Any]:
    """Fetch daily OHLCV bars for a batch of symbols.

    Wraps ``batch_get_stock_data()`` (Polygon.io, thread-pooled) so the
    pattern phase can render chart evidence without touching the walker.
    Returns ``{"symbols": {"AAPL": [{"datetime", "open", "high", "low",
    "close", "volume"}, ...]}}``; failed symbols map to an empty list.
    """
    from stock_analyze.data.polygon import batch_get_stock_data

    pairs = [(s.symbol, s.exchange) for s in body.symbols]
    frames = await asyncio.to_thread(batch_get_stock_data, pairs, n_bars=body.bars)

    out: dict[str, list[dict[str, Any]]] = {}
    for symbol, df in frames.items():
        if df is None or (hasattr(df, "empty") and df.empty):
            out[symbol] = []
            continue
        rows: list[dict[str, Any]] = []
        for idx, bar in df.iterrows():
            dt = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
            rows.append({
                "datetime": dt,
                "open": round(float(bar["open"]), 4),
                "high": round(float(bar["high"]), 4),
                "low": round(float(bar["low"]), 4),
                "close": round(float(bar["close"]), 4),
                "volume": int(bar["volume"]),
            })
        out[symbol] = rows
    return {"symbols": out}
