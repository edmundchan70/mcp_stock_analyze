"""
OHLCV helpers for enrichment fallbacks.

Lazy-loads the root tradingview_data module so EP screener runs without tvDatafeed
installed when force-include enrichment is not needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _ensure_root_on_path() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _tv():
    _ensure_root_on_path()
    import tradingview_data as tv

    return tv


def get_tv_instance(*args, **kwargs):
    return _tv().get_tv_instance(*args, **kwargs)


def get_stock_data(*args, **kwargs):
    return _tv().get_stock_data(*args, **kwargs)


def get_stock_data_pydantic(*args, **kwargs):
    return _tv().get_stock_data_pydantic(*args, **kwargs)


def get_stock_data_dict(*args, **kwargs):
    return _tv().get_stock_data_dict(*args, **kwargs)


def get_stock_data_for_agent(*args, **kwargs):
    return _tv().get_stock_data_for_agent(*args, **kwargs)


def get_multiple_symbols(*args, **kwargs):
    return _tv().get_multiple_symbols(*args, **kwargs)


def enrich_from_ohlcv(symbol: str, exchange: str, n_bars: int = 60) -> dict[str, Any]:
    """
    Build a partial EP row from OHLCV when screener misses a force-include.

    Gap uses open vs prior close; RVOL10 uses last volume / 10d avg volume.
    """
    df = get_stock_data(
        symbol=symbol,
        exchange=exchange,
        interval="daily",
        n_bars=n_bars,
        return_format="dataframe",
    )
    if df is None or len(df) < 11:
        raise ValueError(f"Insufficient OHLCV for {exchange}:{symbol}")

    last = df.iloc[-1]
    prev = df.iloc[-2]
    open_price = float(last["open"])
    prior_close = float(prev["close"])
    close = float(last["close"])
    volume = float(last["volume"])
    hist = df.iloc[:-1]
    window = hist.iloc[-50:] if len(hist) >= 50 else hist
    avg_vol_10 = float(hist["volume"].iloc[-10:].mean()) if len(hist) >= 10 else float(hist["volume"].mean())
    dollar_vol = (window["close"] * window["volume"]).astype(float)
    avg_dollar_50 = float(dollar_vol.mean()) if len(dollar_vol) else 0.0
    rvol10 = volume / avg_vol_10 if avg_vol_10 else 0.0
    gap = (open_price - prior_close) / prior_close * 100.0 if prior_close else 0.0

    return {
        "name": f"{exchange.upper()}:{symbol.upper()}",
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "close": close,
        "open": open_price,
        "prior_close": prior_close,
        "gap": gap,
        "volume": volume,
        "relative_volume_10d_calc": rvol10,
        "Value.Traded": close * volume,
        "avg_dollar_volume_50d": avg_dollar_50,
    }


__all__ = [
    "get_tv_instance",
    "get_stock_data",
    "get_stock_data_pydantic",
    "get_stock_data_dict",
    "get_stock_data_for_agent",
    "get_multiple_symbols",
    "enrich_from_ohlcv",
]
