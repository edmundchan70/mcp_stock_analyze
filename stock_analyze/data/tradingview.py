"""
OHLCV helpers for enrichment fallbacks.

Lazy-loads the root tradingview_data module so EP screener runs without tvDatafeed
installed when force-include enrichment is not needed.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .symbols import US_EXCHANGE_FALLBACK_ORDER

logger = logging.getLogger(__name__)


@dataclass
class EnrichResult:
    """Result of attempting to enrich a single force-include symbol via OHLCV."""

    symbol: str
    exchange: str
    row: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.row is not None


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


def _try_enrich_single(
    symbol: str,
    exchange: str,
    n_bars: int = 60,
    max_retries: int = 1,
) -> dict[str, Any]:
    """Call enrich_from_ohlcv with retry and backoff on one exchange pair."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return enrich_from_ohlcv(symbol, exchange, n_bars)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait = 2**attempt
                logger.info(
                    "[retry] attempt %d/%d %s:%s — %s (waiting %ds)",
                    attempt + 1,
                    max_retries,
                    exchange,
                    symbol,
                    exc,
                    wait,
                )
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def enrich_with_retry(
    symbol: str,
    exchange: str,
    n_bars: int = 60,
    max_retries: int = 1,
) -> EnrichResult:
    """Enrich a force-include symbol with 1-attempt-per-exchange sequential fallback.

    Strategy:
    1. Try the preferred exchange with 1 attempt (WebSocket is fresh per call).
    2. If it fails, try each US exchange in defined fallback order
       (NASDAQ → NYSE → AMEX → BATS → CBOE), one attempt each.
    3. Return an EnrichResult — check ``.ok`` to see if enrichment succeeded.
    """
    errors: list[str] = []

    # 1. Try primary exchange (1 attempt).
    try:
        row = _try_enrich_single(symbol, exchange, n_bars, max_retries=1)
        return EnrichResult(symbol=symbol, exchange=exchange, row=row)
    except Exception as exc:
        primary_err = f"{exchange}: {exc}"
        errors.append(primary_err)
        logger.warning(
            "[enrich] primary %s:%s failed: %s",
            exchange,
            symbol,
            exc,
        )

    # 2. Try fallback exchanges sequentially, one attempt each.
    for fb_exch in US_EXCHANGE_FALLBACK_ORDER:
        if fb_exch.upper() == exchange.upper():
            continue  # already tried
        try:
            row = _try_enrich_single(symbol, fb_exch, n_bars, max_retries=1)
            logger.info(
                "[enrich] %s succeeded on fallback exchange %s (was %s)",
                symbol,
                fb_exch,
                exchange,
            )
            return EnrichResult(symbol=symbol, exchange=fb_exch, row=row)
        except Exception as exc:
            errors.append(f"{fb_exch}: {exc}")

    return EnrichResult(symbol=symbol, exchange=exchange, errors=errors)


__all__ = [
    "EnrichResult",
    "enrich_from_ohlcv",
    "enrich_with_retry",
    "get_tv_instance",
    "get_stock_data",
    "get_stock_data_pydantic",
    "get_stock_data_dict",
    "get_stock_data_for_agent",
    "get_multiple_symbols",
]
