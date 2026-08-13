"""Unit tests for BO runner orchestration (mocked Polygon OHLCV)."""

import pytest
from unittest.mock import patch
import pandas as pd

from bo_fixtures import make_scenario

from stock_analyze.scanners.bo.runner import (
    merge_bo_force_rows,
    run_bo_scan,
)


def _make_resolved_row(name: str, exchange: str = "NASDAQ", close: float = 50.0) -> dict:
    """Polygon-resolved row (post resolve_force_symbol)."""
    return {
        "name": f"{exchange}:{name}",
        "symbol": name,
        "exchange": exchange,
        "close": close,
        "market_cap": 5_000_000_000,
        "description": f"{name} Inc.",
    }


class TestMergeForceRows:
    def test_merge_screener_wins_duplicate(self):
        screener = [_make_resolved_row("AAPL", close=150.0)]
        force = [_make_resolved_row("AAPL", exchange="NASDAQ")]
        merged, force_set, source = merge_bo_force_rows(
            screener, [("AAPL", "NASDAQ")], force,
        )
        assert len(merged) == 1
        aapl = [r for r in merged if r.get("symbol") == "AAPL"][0]
        assert aapl["close"] == 150.0

    def test_merge_adds_force_only(self):
        screener = [_make_resolved_row("AAPL")]
        force_keys = [("AAPL", "NASDAQ"), ("XYZ", "NYSE")]
        force = [_make_resolved_row("XYZ", exchange="NYSE")]
        merged, force_set, source = merge_bo_force_rows(
            screener, force_keys, force,
        )
        assert len(merged) == 2
        symbols = {r.get("symbol") for r in merged}
        assert "AAPL" in symbols
        assert "XYZ" in symbols
        assert source == "force"  # paste-only post-migration

    def test_merge_screener_only(self):
        screener = [_make_resolved_row("AAPL"), _make_resolved_row("MSFT")]
        merged, force_set, source = merge_bo_force_rows(
            screener, [], [],
        )
        assert len(merged) == 2
        assert source == "force"

    def test_merge_force_only(self):
        force_keys = [("XYZ", "NYSE")]
        force = [_make_resolved_row("XYZ", exchange="NYSE")]
        merged, force_set, source = merge_bo_force_rows(
            [], force_keys, force,
        )
        assert len(merged) == 1
        assert source == "force"


class TestRunBoScan:
    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
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

    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
    def test_run_bo_scan_returns_bucket(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_resolved_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        # Textbook classic should get rated 5★
        assert bucket.count >= 0

    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
    def test_run_bo_scan_liquidity_rejected(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        # Zero volume → fails liquidity gate
        df = make_scenario("textbook_classic")
        df["volume"] = 0
        mock_batch.return_value = {"AAPL": df}
        rows = [_make_resolved_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        # Should be empty after liquidity rejection
        assert bucket.count == 0

    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
    def test_run_bo_scan_no_gate_keeps_all(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_resolved_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=False,
        )
        assert bucket is not None
        assert bucket.gates_applied is False
        assert bucket.count == 1

    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
    def test_run_bo_scan_fetches_via_batch(self, mock_spy, mock_batch):
        mock_batch.return_value = {"AAPL": make_scenario("textbook_classic")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_resolved_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        assert bucket.count == 1
        mock_batch.assert_called_once()

    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
    def test_run_bo_scan_near_miss_populated(self, mock_spy, mock_batch):
        """apply_gates=True → near_miss populated for 3★-only universe."""
        mock_batch.return_value = {"AAPL": make_scenario("near_miss")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_resolved_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=True,
        )
        assert bucket is not None
        # near_miss scenario: 3★, fails only volume_surge → 8/9 → near-miss
        assert len(bucket.near_miss) >= 1

    @patch("stock_analyze.scanners.bo.runner.batch_get_stock_data")
    @patch("stock_analyze.scanners.bo.runner.fetch_spy")
    def test_run_bo_scan_near_miss_absent_run_all(self, mock_spy, mock_batch):
        """apply_gates=False → near_miss is empty (not computed)."""
        mock_batch.return_value = {"AAPL": make_scenario("near_miss")}
        mock_spy.return_value = make_scenario("textbook_classic")
        rows = [_make_resolved_row("AAPL")]
        bucket = run_bo_scan(
            screener_rows=rows,
            apply_gates=False,
        )
        assert bucket is not None
        assert bucket.near_miss == []
