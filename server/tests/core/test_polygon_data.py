"""Tests for Polygon.io data adapter (stock_analyze/data/polygon.py)."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pandas as pd
import pytest
from dotenv import load_dotenv

from stock_analyze.data.polygon import (
    _mic_to_exchange,
    _reset_client,
    batch_get_stock_data,
    fetch_market_snapshot,
    fetch_spy,
    get_stock_data,
    get_stock_data_dict,
    get_stock_data_for_agent,
    prefilter_snapshot,
    resolve_force_symbol,
    resolve_market_caps,
    to_ep_row,
)


# ── helpers ──────────────────────────────────────────────────────


def _make_agg_rows(n: int = 300, base: float = 100.0) -> list:
    """Build synthetic Polygon agg objects."""
    import numpy as np
    rows = []
    base_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    for i in range(n):
        close = base + i * 0.5
        rows.append(SimpleNamespace(
            timestamp=base_ts + i * 86400000,
            open=close - 0.2,
            high=close + 0.8,
            low=close - 0.8,
            close=close,
            volume=1_000_000 + i * 10,
        ))
    return rows


def _make_ticker_details(**overrides) -> SimpleNamespace:
    defaults = {
        "primary_exchange": "XNAS",
        "market_cap": 5_000_000_000,
        "description": "Test Company Inc.",
        "share_class_shares_outstanding": 1_000_000,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── MIC mapping ───────────────────────────────────────────────────


class TestMicMapping:
    def test_xnas_to_nasdaq(self):
        assert _mic_to_exchange("XNAS") == "NASDAQ"

    def test_xnys_to_nyse(self):
        assert _mic_to_exchange("XNYS") == "NYSE"

    def test_xase_to_amex(self):
        assert _mic_to_exchange("XASE") == "AMEX"

    def test_unknown_mic_returns_nasdaq(self):
        assert _mic_to_exchange("XTSE") == "NASDAQ"

    def test_none_returns_nasdaq(self):
        assert _mic_to_exchange(None) == "NASDAQ"


# ── get_stock_data ────────────────────────────────────────────────


class TestGetStockData:
    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_returns_dataframe(self, mock_fetch):
        df_mock = pd.DataFrame({
            "open": [100.0] * 300,
            "high": [105.0] * 300,
            "low": [95.0] * 300,
            "close": [102.0] * 300,
            "volume": [1000000] * 300,
        })
        mock_fetch.return_value = df_mock

        _reset_client()
        df = get_stock_data("AAPL", n_bars=300)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 300

    @patch("stock_analyze.data.polygon._get_client")
    def test_handles_api_error(self, mock_client):
        client = MagicMock()
        client.get_aggs.side_effect = Exception("API error")
        mock_client.return_value = client

        _reset_client()
        df = get_stock_data("UNKNOWN", n_bars=300)
        assert isinstance(df, pd.DataFrame)
        assert df.empty


# ── batch_get_stock_data ──────────────────────────────────────────


class TestBatchGetStockData:
    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_batch_returns_symbol_map(self, mock_fetch):
        df = pd.DataFrame({
            "open": [100.0] * 2, "high": [101.0] * 2,
            "low": [99.0] * 2, "close": [100.0] * 2,
            "volume": [1_000_000] * 2,
        })
        mock_fetch.return_value = df

        symbols = [("AAPL", "NASDAQ"), ("MSFT", "NASDAQ")]
        result = batch_get_stock_data(symbols, n_bars=300)

        assert len(result) == 2
        assert "AAPL" in result
        assert "MSFT" in result

    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_soft_fail_per_symbol(self, mock_fetch):
        def _side_effect(sym, **kwargs):
            if sym == "FAIL":
                return pd.DataFrame()
            df = pd.DataFrame({
                "open": [100.0], "high": [101.0], "low": [99.0],
                "close": [100.0], "volume": [1_000_000],
            })
            return df

        mock_fetch.side_effect = _side_effect

        symbols = [("AAPL", "NASDAQ"), ("FAIL", "NASDAQ")]
        result = batch_get_stock_data(symbols, n_bars=300)

        assert "AAPL" in result
        assert "FAIL" in result
        assert result["FAIL"] is None


# ── resolve_force_symbol ──────────────────────────────────────────


class TestResolveForceSymbol:
    @patch("stock_analyze.data.polygon._get_client")
    def test_resolves_nasdaq_symbol(self, mock_client):
        client = MagicMock()
        client.get_ticker_details.return_value = _make_ticker_details(
            primary_exchange="XNAS", market_cap=3_000_000_000
        )
        mock_client.return_value = client

        _reset_client()
        result = resolve_force_symbol("AAPL")
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["exchange"] == "NASDAQ"
        assert result["market_cap"] == 3_000_000_000

    @patch("stock_analyze.data.polygon._get_client")
    def test_returns_none_on_failure(self, mock_client):
        client = MagicMock()
        client.get_ticker_details.side_effect = Exception("Not found")
        mock_client.return_value = client

        _reset_client()
        result = resolve_force_symbol("UNKNOWN")
        assert result is None


# ── to_ep_row ─────────────────────────────────────────────────────


class TestToEpRow:
    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_computes_ep_metrics(self, mock_fetch):
        import numpy as np
        n = 300
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        closes = 100.0 + np.arange(n) * 0.1
        df = pd.DataFrame({
            "open": closes - 0.3,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": [1_000_000] * n,
        }, index=idx)
        mock_fetch.return_value = df

        row = to_ep_row("AAPL", n_bars=300)
        assert row["symbol"] == "AAPL"
        assert "gap" in row
        assert "relative_volume_10d_calc" in row
        assert "Value.Traded" in row
        assert "avg_dollar_volume_50d" in row

    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_raises_on_insufficient_data(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        with pytest.raises(ValueError):
            to_ep_row("AAPL", n_bars=300)


# ── fetch_spy ─────────────────────────────────────────────────────


class TestFetchSpy:
    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_returns_dataframe(self, mock_fetch):
        df = pd.DataFrame({
            "open": [500.0], "high": [505.0], "low": [495.0],
            "close": [502.0], "volume": [10_000_000],
        })
        mock_fetch.return_value = df

        result = fetch_spy()
        assert isinstance(result, pd.DataFrame)

    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_returns_empty_on_failure(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        result = fetch_spy()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ── get_stock_data_dict ───────────────────────────────────────────


class TestGetStockDataDict:
    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_returns_serializable_dict(self, mock_fetch):
        df = pd.DataFrame({
            "open": [100.0, 101.0], "high": [102.0, 103.0],
            "low": [99.0, 98.0], "close": [101.0, 102.0],
            "volume": [1_000_000, 1_100_000],
        })
        mock_fetch.return_value = df

        result = get_stock_data_dict("AAPL")
        assert result["symbol"] == "AAPL"
        assert len(result["data"]) == 2
        assert "summary" in result
        # Should be JSON serializable
        json.dumps(result)

    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_handles_empty_dataframe(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        result = get_stock_data_dict("UNKNOWN")
        assert result["symbol"] == "UNKNOWN"
        assert result["data"] == []


# ── get_stock_data_for_agent ──────────────────────────────────────


class TestGetStockDataForAgent:
    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_returns_string(self, mock_fetch):
        df = pd.DataFrame({
            "open": [100.0], "high": [102.0], "low": [99.0],
            "close": [101.0], "volume": [1_000_000],
        })
        mock_fetch.return_value = df

        result = get_stock_data_for_agent("AAPL")
        assert isinstance(result, str)
        assert "AAPL" in result

    @patch("stock_analyze.data.polygon._fetch_aggs")
    def test_handles_empty_dataframe(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        result = get_stock_data_for_agent("UNKNOWN")
        assert isinstance(result, str)
        assert "No data" in result


# ── market snapshot sweep ──────────────────────────────────────────


def _make_snapshot(
    ticker: str,
    day_close: float,
    day_volume: float,
    prev_close: float,
    prev_volume: float,
    change: float = 0.5,
) -> SimpleNamespace:
    """Build a synthetic Polygon ``TickerSnapshot`` object."""
    day = SimpleNamespace(
        open=day_close - 0.2, high=day_close + 0.8, low=day_close - 0.8,
        close=day_close, volume=day_volume, vwap=None, timestamp=None,
        transactions=None, otc=None,
    )
    prev = SimpleNamespace(
        open=prev_close - 0.2, high=prev_close + 0.8, low=prev_close - 0.8,
        close=prev_close, volume=prev_volume, vwap=None, timestamp=None,
        transactions=None, otc=None,
    )
    return SimpleNamespace(
        ticker=ticker, day=day, prev_day=prev,
        todays_change=None, todays_change_percent=change,
        updated=None, fair_market_value=None,
    )


class TestMarketSnapshot:
    @patch("stock_analyze.data.polygon._get_client")
    def test_returns_rows_preferring_prev_day(self, mock_client):
        client = MagicMock()
        client.get_snapshot_all.return_value = [
            _make_snapshot("AAPL", 150.0, 1_000, 149.0, 2_000_000, 1.2),
            _make_snapshot("MSFT", 400.0, 1_000, 399.0, 3_000_000, -0.4),
        ]
        mock_client.return_value = client

        _reset_client()
        rows = fetch_market_snapshot()

        assert len(rows) == 2
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["exchange"] == "NASDAQ"
        assert rows[0]["price"] == 149.0  # prev_day close wins
        assert rows[0]["dollar_volume_proxy"] == pytest.approx(149.0 * 2_000_000)
        assert rows[0]["change_pct"] == 1.2
        assert rows[1]["symbol"] == "MSFT"

    @patch("stock_analyze.data.polygon._get_client")
    def test_returns_empty_on_failure(self, mock_client):
        client = MagicMock()
        client.get_snapshot_all.side_effect = Exception("snapshot down")
        mock_client.return_value = client

        _reset_client()
        assert fetch_market_snapshot() == []


class TestPrefilterSnapshot:
    def test_filters_price_and_dollar_volume(self):
        rows = [
            {"symbol": "A", "price": 5.0, "dollar_volume_proxy": 50_000_000},    # price too low
            {"symbol": "B", "price": 20.0, "dollar_volume_proxy": 1_000_000},   # dollar vol too low
            {"symbol": "C", "price": 20.0, "dollar_volume_proxy": 50_000_000},  # passes
            {"symbol": "D", "price": None, "dollar_volume_proxy": None},         # missing
        ]
        out = prefilter_snapshot(rows, min_price=10.0, min_dollar_vol=10_000_000)
        assert [r["symbol"] for r in out] == ["C"]


class TestResolveMarketCaps:
    @patch("stock_analyze.data.polygon.resolve_force_symbol")
    def test_keeps_only_above_min_mcap(self, mock_resolve):
        def _resolve(sym):
            if sym == "SMALL":
                return {
                    "name": "NASDAQ:SMALL", "symbol": "SMALL", "exchange": "NASDAQ",
                    "market_cap": 100_000_000, "description": "", "close": None,
                }
            if sym == "MISSING":
                return None
            return {
                "name": "NASDAQ:BIG", "symbol": sym, "exchange": "NASDAQ",
                "market_cap": 5_000_000_000, "description": "", "close": None,
            }

        mock_resolve.side_effect = _resolve
        out = resolve_market_caps(["BIG", "SMALL", "MISSING"], min_mcap=300_000_000)
        assert [r["symbol"] for r in out] == ["BIG"]

    @patch("stock_analyze.data.polygon.resolve_force_symbol")
    def test_empty_input(self, mock_resolve):
        assert resolve_market_caps([]) == []
        mock_resolve.assert_not_called()


# ── integration tests (real Polygon API, skipped without key) ─────


def _polygon_api_key_is_set() -> bool:
    load_dotenv()
    key = os.getenv("POLYGON_API_KEY", "").strip()
    return bool(key) and key != "<your polygon.io API key>"


@pytest.mark.integration
class TestPolygonApiIntegration:
    """Verify both Polygon SDK endpoints return well-formed data against the live API."""

    def test_ticker_details_real_api(self):
        if not _polygon_api_key_is_set():
            pytest.skip("POLYGON_API_KEY not set")

        _reset_client()
        result = resolve_force_symbol("AAPL")

        assert result is not None, "resolve_force_symbol returned None for AAPL"
        assert isinstance(result, dict)
        assert result["symbol"] == "AAPL"
        assert result["exchange"] in ("NASDAQ", "NYSE", "AMEX")
        assert isinstance(result["market_cap"], (int, float)), (
            f"market_cap must be numeric, got {type(result['market_cap']).__name__}"
        )
        assert result["market_cap"] > 0, "market_cap must be positive"
        assert isinstance(result["description"], str)
        assert result["close"] is not None, "close must not be None"

    def test_get_aggs_real_api(self):
        if not _polygon_api_key_is_set():
            pytest.skip("POLYGON_API_KEY not set")

        _reset_client()
        df = get_stock_data("AAPL")

        assert isinstance(df, pd.DataFrame), f"expected DataFrame, got {type(df).__name__}"
        assert not df.empty, "DataFrame is empty"
        assert 100 <= len(df) <= 500, f"expected 100–500 bars, got {len(df)}"

        expected_cols = {"open", "high", "low", "close", "volume"}
        missing = expected_cols - set(df.columns)
        assert not missing, f"missing columns: {missing}"

        assert df["close"].iloc[-1] > 0, "last close must be positive"
        assert df["volume"].min() >= 0, "volume must be non-negative"

        # Smoke-test fetch_spy too
        spy = fetch_spy()
        assert isinstance(spy, pd.DataFrame)
        assert not spy.empty
        assert spy["close"].iloc[-1] > 0, "SPY close must be positive"
