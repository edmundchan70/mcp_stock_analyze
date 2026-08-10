"""Unit tests for BO runner orchestration (mocked OHLCV)."""

import pytest
from unittest.mock import patch
import pandas as pd

from bo_fixtures import make_scenario

from stock_analyze.scanners.bo.runner import (
    merge_bo_force_rows,
    run_bo_scan,
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
        merged, force_set, source = merge_bo_force_rows(
            screener, [("AAPL", "NASDAQ")], force,
        )
        assert len(merged) == 1
        aapl = [r for r in merged if r.get("symbol") == "AAPL"][0]
        assert aapl["close"] == 150.0

    def test_merge_adds_force_only(self):
        screener = [_make_screener_row("AAPL")]
        force_keys = [("AAPL", "NASDAQ"), ("XYZ", "NYSE")]
        force = [_make_force_row("XYZ", exchange="NYSE")]
        merged, force_set, source = merge_bo_force_rows(
            screener, force_keys, force,
        )
        assert len(merged) == 2
        symbols = {r.get("symbol") for r in merged}
        assert "AAPL" in symbols
        assert "XYZ" in symbols
        assert source == "hybrid"

    def test_merge_screener_only(self):
        screener = [_make_screener_row("AAPL"), _make_screener_row("MSFT")]
        merged, force_set, source = merge_bo_force_rows(
            screener, [], [],
        )
        assert len(merged) == 2
        assert source == "screener"

    def test_merge_force_only(self):
        force_keys = [("XYZ", "NYSE")]
        force = [_make_force_row("XYZ", exchange="NYSE")]
        merged, force_set, source = merge_bo_force_rows(
            [], force_keys, force,
        )
        assert len(merged) == 1
        assert source == "force"


class TestRunBoScan:
    @patch("tradingview_data.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner._fetch_spy")
    def test_run_bo_scan_empty_input(self, mock_spy, mock_batch):
        mock_batch.return_value = {}
        mock_spy.return_value = make_scenario("textbook_classic")
        bucket = run_bo_scan(
            screener_rows=[],
            force_keys=set(),
            force_rows=[],
            apply_gates=True,
        )
        assert bucket.count == 0

    @patch("tradingview_data.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner._fetch_spy")
    def test_run_bo_scan_rates_textbook(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_screener_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        assert bucket.count == 1
        assert len(bucket.five_star) == 1

    @patch("tradingview_data.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner._fetch_spy")
    def test_run_bo_scan_gates_three_star(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("near_miss")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_screener_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        assert bucket.count == 1
        assert len(bucket.five_star) == 0
        assert len(bucket.four_star) == 0
        assert len(bucket.three_star) == 1

    @patch("tradingview_data.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner._fetch_spy")
    def test_run_bo_scan_no_gate_keeps_all(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_screener_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=False,
        )
        assert bucket is not None
        assert bucket.gates_applied is False
        assert bucket.count == 1

    @patch("tradingview_data.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner._fetch_spy")
    def test_run_bo_scan_fetches_via_batch(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_screener_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        assert bucket.count == 1
        mock_batch.assert_called_once()
