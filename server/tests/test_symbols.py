"""Tests for POST /api/ohlcv (pattern-phase chart evidence)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.main import create_app


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [10.0, 10.5, 10.8],
            "high": [10.6, 11.0, 11.2],
            "low": [9.8, 10.2, 10.6],
            "close": [10.4, 10.9, 11.1],
            "volume": [1_000_000, 1_200_000, 1_500_000],
        },
        index=pd.to_datetime(["2026-08-14", "2026-08-15", "2026-08-16"]),
    )


@pytest.mark.asyncio
async def test_ohlcv_returns_serialized_bars(monkeypatch):
    import httpx

    import stock_analyze.data.polygon as polygon

    monkeypatch.setattr(
        polygon,
        "batch_get_stock_data",
        lambda symbols, n_bars=300: {"AAPL": _frame(), "MSFT": None},
    )

    app = create_app(repo=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/ohlcv",
            json={"symbols": [{"symbol": "AAPL"}, {"symbol": "MSFT"}], "bars": 300},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["symbols"].keys()) == {"AAPL", "MSFT"}
        bars = data["symbols"]["AAPL"]
        assert len(bars) == 3
        assert bars[0] == {
            "datetime": "2026-08-14T00:00:00",
            "open": 10.0,
            "high": 10.6,
            "low": 9.8,
            "close": 10.4,
            "volume": 1_000_000,
        }
        assert data["symbols"]["MSFT"] == []


@pytest.mark.asyncio
async def test_ohlcv_rejects_empty_symbols():
    import httpx

    app = create_app(repo=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/ohlcv", json={"symbols": []})
        assert resp.status_code == 422
