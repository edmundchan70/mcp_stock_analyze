from stock_analyze.data.screener import _is_us_listed


def test_otc_symbols_are_not_us_listed():
    assert _is_us_listed({"name": "OTC:NGMC", "exchange": "OTC"}) is False


def test_nasdaq_symbols_are_us_listed():
    assert _is_us_listed({"name": "NASDAQ:AAPL", "exchange": "NASDAQ"}) is True
