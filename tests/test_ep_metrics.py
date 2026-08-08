"""Seam: normalize screener / raw rows into EpStock metrics."""

from datetime import date

from stock_analyze.scanners.ep.metrics import compute_gap_pct, normalize_row


def test_gap_pct_is_open_vs_prior_close():
    # (110 - 100) / 100 = 10%
    assert compute_gap_pct(open_price=110.0, prior_close=100.0) == 10.0


def test_normalize_row_maps_tradingview_fields():
    stock = normalize_row(
        {
            "name": "NASDAQ:AAPL",
            "close": 198.5,
            "open": 195.0,
            "gap": 8.2,
            "relative_volume_10d_calc": 3.1,
            "market_cap_basic": 2_500_000_000,
            "AvgValue.Traded_60d": 12_500_000,
            "Value.Traded": 40_000_000,
            "exchange": "NASDAQ",
        },
        as_of=date(2026, 8, 8),
        force_included=False,
    )
    assert stock.symbol == "AAPL"
    assert stock.exchange == "NASDAQ"
    assert stock.price == 198.5
    assert stock.gap_pct == 8.2
    assert stock.rvol10 == 3.1
    assert stock.market_cap == 2_500_000_000
    assert stock.event_dollar_volume == 40_000_000
    assert stock.avg_dollar_volume_50d == 12_500_000.0


def test_normalize_prefers_computed_gap_from_open_and_prior_close():
    stock = normalize_row(
        {
            "name": "NASDAQ:GAP",
            "close": 110.0,
            "open": 110.0,
            "prior_close": 100.0,
            "gap": 99.0,  # stale / wrong — must not win over open/prior_close
            "relative_volume_10d_calc": 2.0,
        },
        as_of=date(2026, 8, 8),
    )
    assert stock.gap_pct == 10.0


def test_normalize_row_computes_gap_when_gap_column_missing():
    stock = normalize_row(
        {
            "name": "NYSE:XYZ",
            "close": 20.0,
            "open": 21.0,
            "prior_close": 20.0,
            "relative_volume_10d_calc": 2.0,
            "volume": 1_000_000,
        },
        as_of=date(2026, 8, 8),
    )
    assert stock.symbol == "XYZ"
    assert stock.exchange == "NYSE"
    assert stock.gap_pct == 5.0
    assert stock.event_dollar_volume == 20_000_000.0
