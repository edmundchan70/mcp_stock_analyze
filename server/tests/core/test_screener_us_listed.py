import os
import sys

import pandas as pd
import pytest

from stock_analyze.data.screener import _is_us_listed, fetch_symbols
from stock_analyze.data.symbols import row_symbol_key

pytestmark = pytest.mark.screener


# ── existing tests ──────────────────────────────────────────────────────


def test_otc_symbols_are_not_us_listed():
    assert _is_us_listed({"name": "OTC:NGMC", "exchange": "OTC"}) is False


def test_nasdaq_symbols_are_us_listed():
    assert _is_us_listed({"name": "NASDAQ:AAPL", "exchange": "NASDAQ"}) is True


# ── helpers ─────────────────────────────────────────────────────────────


class _CapturedQuery:
    """Drop-in mock for tradingview_screener.Query that records config."""

    def __init__(self):
        self._select: list[str] = []
        self._where = None
        self._markets: str | None = None
        self._limit_val: int | None = None
        self._has_tickers = False
        self._has_symbols = False
        self._fake_rows: list[dict] = []

    def select(self, *cols):
        self._select = list(cols)
        return self

    def where(self, *conditions):
        self._where = conditions
        return self

    def set_markets(self, markets):
        self._markets = markets
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def set_tickers(self, *args, **kwargs):
        self._has_tickers = True
        return self

    def set_symbols(self, **kwargs):
        self._has_symbols = True
        return self

    def get_scanner_data(self):
        df = pd.DataFrame(self._fake_rows)
        self._df = df
        return len(df), df


class _CapturedCol:
    """Mock for tradingview_screener.col()."""

    def __init__(self, name):
        self._name = name

    def isin(self, names):
        return {"left": self._name, "operation": "in_range", "right": sorted(names)}


def _install_mock_tradingview(monkeypatch):
    """Insert a mock ``tradingview_screener`` module into sys.modules."""
    import types

    mod = types.ModuleType("tradingview_screener")
    mod.Query = _CapturedQuery
    mod.query = types.ModuleType("tradingview_screener.query")
    mod.col = lambda name: _CapturedCol(name)
    mod.query.Query = mod.Query
    mod.query.col = mod.col

    monkeypatch.setitem(sys.modules, "tradingview_screener", mod)
    monkeypatch.setitem(sys.modules, "tradingview_screener.query", mod.query)


def _build_captured(monkeypatch, fake_rows=None):
    """Install mock and return a factory; calls to fetch_symbols land on the
    most-recently created _CapturedQuery."""
    capture = []
    mod_mock = sys.modules.get("tradingview_screener")
    if mod_mock is None:
        _install_mock_tradingview(monkeypatch)
        mod_mock = sys.modules["tradingview_screener"]

    class _Q(_CapturedQuery):
        def __init__(self):
            super().__init__()
            self._fake_rows = list(fake_rows or [])
            capture.clear()
            capture.append(self)

    mod_mock.Query = _Q
    return capture


def _force_keys(*syms):
    return [(s, "NASDAQ") for s in syms]


# ── fetch_symbols unit tests ───────────────────────────────────────────


def test_fetch_symbols_empty_input_returns_empty(monkeypatch):
    _install_mock_tradingview(monkeypatch)
    assert fetch_symbols([]) == []
    assert fetch_symbols([("", "NASDAQ"), (" ", "NYSE")]) == []


def test_fetch_symbols_filters_bare_names_without_exchange_prefix(monkeypatch):
    cap = _build_captured(monkeypatch)
    fetch_symbols(_force_keys("JHX", "KGC", "LUNR"), limit=200)

    q = cap[0]
    # markets set to america
    assert q._markets == "america"
    # no ticker/symbol dictionaries set (exchange prefix path locked out)
    assert not q._has_tickers
    assert not q._has_symbols
    # where filter uses bare names
    assert q._where is not None
    filt = q._where[0]
    assert filt["left"] == "name"
    assert "JHX" in filt["right"]
    assert "KGC" in filt["right"]
    assert "LUNR" in filt["right"]


def test_fetch_symbols_returns_normalized_rows_with_real_exchange(monkeypatch):
    cap = _build_captured(
        monkeypatch,
        fake_rows=[
            {"name": "NYSE:JHX", "close": 25.0, "exchange": "NYSE"},
            {"name": "NASDAQ:LUNR", "close": 8.0, "exchange": "NASDAQ"},
        ],
    )
    rows = fetch_symbols(_force_keys("JHX", "LUNR"))
    assert len(rows) == 2

    keys = {row_symbol_key(r) for r in rows}
    assert ("JHX", "NYSE") in keys
    assert ("LUNR", "NASDAQ") in keys


def test_fetch_symbols_bumps_limit_for_large_paste(monkeypatch):
    cap = _build_captured(monkeypatch)
    syms = [(f"TICKER{i:03d}", "NASDAQ") for i in range(250)]
    fetch_symbols(syms, limit=200)
    assert cap[0]._limit_val >= 250


# ── opt-in live smoke test ──────────────────────────────────────────────


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"),
    reason="set RUN_LIVE_TESTS=1 to exercise real TradingView screener",
)
def test_live_fetch_symbols_resolves_all_pasted():
    """Real screener must resolve JHX, KGC, LUNR, MB without websocket fallback."""
    rows = fetch_symbols(
        [("JHX", "NASDAQ"), ("KGC", "NYSE"), ("LUNR", "NASDAQ"), ("MB", "NASDAQ")],
        limit=10,
    )
    found = {row_symbol_key(r) for r in rows}
    pasted = {"JHX", "KGC", "LUNR", "MB"}
    resolved_symbols = {sym for sym, _ in found}
    assert pasted <= resolved_symbols, f"Missing: {pasted - resolved_symbols}"
