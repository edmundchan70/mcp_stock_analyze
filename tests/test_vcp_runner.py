"""Unit tests for VCP runner orchestration (mocked OHLCV)."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
from datetime import datetime

from stock_analyze.scanners.vcp.runner import (
    merge_vcp_force_rows,
    run_vcp_scan,
)


def _make_screener_row(name: str, close: float = 50.0) -> dict:
    return {
        "name": f"NASDAQ:{name}",
        "symbol": name,
        "exchange": "NASDAQ",
        "close": close,
        "SMA50": close - 1,
        "SMA200": close - 3,
        "volume": 1_000_000,
        "average_volume_60d_calc": 500_000,
        "market_cap_basic": 5_000_000_000,
        "description": f"{name} Inc.",
    }


def _make_force_row(name: str, exchange: str = "NYSE") -> dict:
    return {
        "name": f"{exchange}:{name}",
        "symbol": name,
        "exchange": exchange,
        "close": 25.0,
        "volume": 500_000,
    }


class TestMergeForceRows:
    def test_merge_screener_wins_duplicate(self):
        screener = [_make_screener_row("AAPL", close=150.0)]
        force = [_make_force_row("AAPL", exchange="NASDAQ")]
        merged, force_set, source = merge_vcp_force_rows(
            screener, [("AAPL", "NASDAQ")], force,
        )
        assert len(merged) == 1
        # Screener close should win
        aapl = [r for r in merged if r.get("symbol") == "AAPL"][0]
        assert aapl["close"] == 150.0

    def test_merge_adds_force_only(self):
        screener = [_make_screener_row("AAPL")]
        force_keys = [("AAPL", "NASDAQ"), ("XYZ", "NYSE")]
        force = [_make_force_row("XYZ", exchange="NYSE")]
        merged, force_set, source = merge_vcp_force_rows(
            screener, force_keys, force,
        )
        assert len(merged) == 2
        symbols = {r.get("symbol") for r in merged}
        assert "AAPL" in symbols
        assert "XYZ" in symbols
        assert source == "hybrid"

    def test_merge_screener_only(self):
        screener = [_make_screener_row("AAPL"), _make_screener_row("MSFT")]
        merged, force_set, source = merge_vcp_force_rows(
            screener, [], [],
        )
        assert len(merged) == 2
        assert source == "screener"

    def test_merge_force_only(self):
        force_keys = [("XYZ", "NYSE")]
        force = [_make_force_row("XYZ", exchange="NYSE")]
        merged, force_set, source = merge_vcp_force_rows(
            [], force_keys, force,
        )
        assert len(merged) == 1
        assert source == "force"


class TestRunVcpScan:
    @patch("stock_analyze.scanners.vcp.runner.get_stock_data")
    def test_run_vcp_scan_empty_input(self, mock_get_stock):
        mock_get_stock.return_value = _make_ohlcv_uptrend(300)
        bucket = run_vcp_scan(
            screener_rows=[],
            force_keys=set(),
            force_rows=[],
            apply_gates=True,
        )
        assert bucket.count == 0

    @patch("stock_analyze.scanners.vcp.runner.get_stock_data")
    @patch("stock_analyze.scanners.vcp.runner._fetch_spy")
    def test_run_vcp_scan_with_gate(self, mock_spy, mock_get_stock):
        mock_get_stock.return_value = _make_ohlcv_uptrend(300)
        mock_spy.return_value = _make_ohlcv_uptrend(300, base=500)
        rows = [_make_screener_row("AAPL"), _make_screener_row("MSFT")]
        bucket = run_vcp_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        assert bucket.count >= 0


def _make_ohlcv_uptrend(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """Create a simple uptrend OHLCV for tests."""
    import numpy as np
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = np.linspace(base, base * 1.2, n)
    return pd.DataFrame(
        {
            "open": closes - 0.1,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )
