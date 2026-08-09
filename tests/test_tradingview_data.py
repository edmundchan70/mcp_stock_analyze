"""Seams: US_EXCHANGE_FALLBACK_ORDER, enrich_with_retry, _try_enrich_single, _close_tv_socket."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from stock_analyze.data.symbols import US_EXCHANGE_FALLBACK_ORDER
from stock_analyze.data.tradingview import EnrichResult, _try_enrich_single, enrich_with_retry


# ── US_EXCHANGE_FALLBACK_ORDER ────────────────────────────────────────


def test_us_exchange_fallback_order_is_correct():
    assert US_EXCHANGE_FALLBACK_ORDER == ("NASDAQ", "NYSE", "AMEX", "BATS", "CBOE")


# ── _try_enrich_single (1 attempt per exchange) ───────────────────────


def test_try_enrich_single_succeeds_first_try():
    with patch(
        "stock_analyze.data.tradingview.enrich_from_ohlcv",
        return_value={"symbol": "AAPL", "exchange": "NASDAQ", "close": 150.0},
    ):
        row = _try_enrich_single("AAPL", "NASDAQ")
        assert row["symbol"] == "AAPL"


def test_try_enrich_single_only_one_attempt_then_raises():
    """max_retries=1 → no retry loop on failure, raises immediately."""
    call_count = [0]

    def failing_ohlcv(symbol, exchange, n_bars=60):
        call_count[0] += 1
        raise ValueError("no data")

    with patch("stock_analyze.data.tradingview.enrich_from_ohlcv", failing_ohlcv):
        with pytest.raises(ValueError):
            _try_enrich_single("MISSING", "NASDAQ")

    assert call_count[0] == 1


# ── enrich_with_retry ────────────────────────────────────────────────


def test_enrich_with_retry_success_on_primary():
    row = {"symbol": "AAPL", "exchange": "NASDAQ"}
    with patch("stock_analyze.data.tradingview.enrich_from_ohlcv", return_value=row):
        result = enrich_with_retry("AAPL", "NASDAQ")
        assert result.ok
        assert result.row == row
        assert result.exchange == "NASDAQ"


def test_enrich_with_retry_falls_back_to_nyse_when_nasdaq_fails():
    """Primary NASDAQ fails → next in order (NYSE) succeeds."""
    nyse_row = {"symbol": "AAPL", "exchange": "NYSE"}

    def selective_ohlcv(symbol, exchange, n_bars=60):
        if exchange.upper() == "NASDAQ":
            raise ValueError("NASD timeout")
        return nyse_row

    with patch("stock_analyze.data.tradingview.enrich_from_ohlcv", selective_ohlcv):
        result = enrich_with_retry("AAPL", "NASDAQ")
        assert result.ok
        assert result.exchange == "NYSE"
        assert result.row["exchange"] == "NYSE"


def test_enrich_with_retry_skips_already_tried_exchange_in_fallbacks():
    """When primary=NYSE, the fallback loop should skip NYSE (already tried)."""
    call_exchanges = []

    def track_ohlcv(symbol, exchange, n_bars=60):
        call_exchanges.append(exchange.upper())
        raise ValueError("no data")

    with patch("stock_analyze.data.tradingview.enrich_from_ohlcv", track_ohlcv):
        result = enrich_with_retry("JHX", "NYSE")
        assert not result.ok
        # NYSE is both primary and in fallback order → called once
        assert call_exchanges.count("NYSE") == 1


def test_enrich_with_retry_all_exchanges_fail():
    """Every exchange fails → result not ok, errors accumulated."""
    with patch(
        "stock_analyze.data.tradingview.enrich_from_ohlcv",
        side_effect=ValueError("no data"),
    ):
        result = enrich_with_retry("MISSING", "NASDAQ")
        assert not result.ok
        assert result.errors
        # 1 primary + 4 fallbacks (skipping NASDAQ) = 5 failures
        assert len(result.errors) == 5


def test_enrich_with_retry_tries_all_fallback_exchanges():
    """Each fallback exchange (except primary) is tried exactly once."""
    tried = []

    def failing_ohlcv(symbol, exchange, n_bars=60):
        tried.append(exchange.upper())
        raise ValueError("fail")

    with patch("stock_analyze.data.tradingview.enrich_from_ohlcv", failing_ohlcv):
        enrich_with_retry("TEST", "CBOE")
        # CBOE is primary, then NASDAQ, NYSE, AMEX, BATS (skipping CBOE)
        assert tried == ["CBOE", "NASDAQ", "NYSE", "AMEX", "BATS"]


# ── _close_tv_socket ──────────────────────────────────────────────────


def test_close_tv_socket_no_instance_does_not_crash():
    """When the singleton is None, calling _close_tv_socket() is a no-op."""
    import tradingview_data as tv

    with patch.object(tv, "_tv_instance", None):
        # Should not raise
        tv._close_tv_socket()


def test_close_tv_socket_with_instance_no_ws_does_not_crash():
    """When tv instance has no ws attribute, call is a no-op."""
    import tradingview_data as tv

    fake_tv = MagicMock()
    del fake_tv.ws  # no ws attribute
    with patch.object(tv, "_tv_instance", fake_tv):
        tv._close_tv_socket()


def test_close_tv_socket_closes_and_nulls_ws():
    """When tv instance has ws, close it and set to None."""
    import tradingview_data as tv

    fake_ws = MagicMock()
    fake_tv = MagicMock()
    fake_tv.ws = fake_ws

    with patch.object(tv, "_tv_instance", fake_tv):
        tv._close_tv_socket()

    fake_ws.close.assert_called_once()
    assert fake_tv.ws is None


def test_close_tv_socket_survives_ws_close_exception():
    """If ws.close() raises, we still null it and don't propagate."""
    import tradingview_data as tv

    fake_ws = MagicMock()
    fake_ws.close.side_effect = ConnectionError("socket broken")
    fake_tv = MagicMock()
    fake_tv.ws = fake_ws

    with patch.object(tv, "_tv_instance", fake_tv):
        tv._close_tv_socket()  # should not raise

    assert fake_tv.ws is None
