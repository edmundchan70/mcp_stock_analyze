"""Polygon.io data adapter — thin wrapper around the official polygon-api-client SDK.

Replaces the TradingView data path (screener, tvDatafeed WebSocket OHLCV,
exchange-fallback enrichment). Returns the same DataFrame/row shapes so
runner, pipeline, and scanner logic stays intact.

Endpoints used:
- ``RESTClient.get_aggs``            → OHLCV bars (300 daily)
- ``RESTClient.get_ticker_details``  → symbol resolution + exchange + market_cap

"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import pandas as pd
from dotenv import load_dotenv
from polygon import RESTClient as PolygonRESTClient

from stock_analyze.scanners.vcp.gates import (
    MIN_ADV_DOLLAR,
    MIN_MARKET_CAP,
    passes_market_cap_gate,
)

logger = logging.getLogger(__name__)

# ── Pre-market hours (Eastern) ───────────────────────────────────
_PREMARKET_START_HOUR = 4
_PREMARKET_START_MINUTE = 0
_PREMARKET_END_HOUR = 9
_PREMARKET_END_MINUTE = 30
_EASTERN = timezone(timedelta(hours=-5))  # EST; Polygon bars are in exchange local time

# ── MIC → short exchange map ─────────────────────────────────────
_MIC_MAP: dict[str, str] = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
    "XASE": "AMEX",
}
_MIC_FALLBACK = "NASDAQ"


def _mic_to_exchange(mic: str | None) -> str:
    """Map Polygon primary exchange MIC code to short exchange label."""
    if not mic:
        return _MIC_FALLBACK
    return _MIC_MAP.get(mic.strip().upper(), _MIC_FALLBACK)


# ── client singleton ─────────────────────────────────────────────
_client: PolygonRESTClient | None = None


def _get_client() -> PolygonRESTClient:
    """Lazy-init the Polygon RESTClient from POLYGON_API_KEY env var."""
    global _client
    if _client is None:
        load_dotenv()
        api_key = os.getenv("POLYGON_API_KEY", "").strip()
        if not api_key or api_key == "<your polygon.io API key>":
            raise RuntimeError(
                "POLYGON_API_KEY not set. Add it to .env (get a key at https://polygon.io)."
            )
        _client = PolygonRESTClient(api_key=api_key)
        # urllib3.HTTPConnectionPool defaults to maxsize=1 per host.
        # ThreadPoolExecutor(max_workers=5) needs at least 5 connections
        # or threads deadlock waiting for the singleton pool slot.
        _client.client.connection_pool_kw["maxsize"] = 24
    return _client


def _reset_client() -> None:
    """Clear the cached client (useful for testing or key rotation)."""
    global _client
    _client = None


# ── low-level bar fetch ──────────────────────────────────────────


def _fetch_aggs(
    symbol: str,
    n_bars: int = 300,
    *,
    max_retries: int = 5,
) -> pd.DataFrame:
    """Fetch daily adjusted aggregates for *symbol* from Polygon.

    Returns a DataFrame with DatetimeIndex and columns ``open/high/low/close/volume``.
    Returns an empty DataFrame on persistent failure.
    """
    client = _get_client()
    # Window: ~420 calendar days for 300 trading days with buffer
    to_date = date.today()
    from_date = to_date - timedelta(days=420)
    t0 = time.perf_counter()

    for attempt in range(max_retries):
        try:
            aggs = client.get_aggs(
                ticker=symbol,
                multiplier=1,
                timespan="day",
                from_=from_date.strftime("%Y-%m-%d"),
                to=to_date.strftime("%Y-%m-%d"),
                adjusted=True,
                limit=n_bars,
            )
            rows = [
                {
                    "datetime": datetime.fromtimestamp(a.timestamp / 1000.0, tz=timezone.utc),
                    "open": a.open,
                    "high": a.high,
                    "low": a.low,
                    "close": a.close,
                    "volume": a.volume,
                }
                for a in aggs
            ]
            if not rows:
                logger.warning("Polygon: no bars returned for %s", symbol)
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df.set_index("datetime", inplace=True)
            df.sort_index(inplace=True)
            elapsed_s = time.perf_counter() - t0
            if elapsed_s > 10:
                logger.info(
                    "Polygon %s: %d bars fetched in %.1fs", symbol, len(df), elapsed_s,
                )
            return df

        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg or "503" in msg or "502" in msg:
                wait = min(2 ** attempt, 60)
                logger.warning(
                    "Polygon rate/5xx for %s (attempt %d/%d), waiting %ds",
                    symbol, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                continue
            logger.warning("Polygon fetch failed for %s: %s", symbol, exc)
            return pd.DataFrame()

    logger.warning("Polygon: exhausted retries for %s", symbol)
    return pd.DataFrame()


# ── public API ───────────────────────────────────────────────────


def get_stock_data(symbol: str, exchange: str = "NASDAQ", n_bars: int = 300) -> pd.DataFrame:
    """Fetch daily OHLCV for a single symbol.

    Returns a DataFrame with DatetimeIndex and columns ``open/high/low/close/volume``.
    The *exchange* parameter is accepted for API compatibility but ignored
    (Polygon resolves symbols globally).
    """
    return _fetch_aggs(symbol, n_bars=n_bars)


def batch_get_stock_data(
    symbols: list[tuple[str, str]],
    n_bars: int = 300,
    refresh_every: int = 50,
    inter_fetch_delay: float = 0.0,
    on_progress: Callable[[int, int, str, str], None] | None = None,
    max_workers: int = 20,
    **kwargs: Any,
) -> dict[str, pd.DataFrame]:
    """Batch-fetch daily OHLCV for many symbols via ThreadPoolExecutor.

    Args:
        symbols: List of ``(symbol, exchange)`` tuples. Exchange is ignored.
        n_bars: Number of daily bars per symbol.
        refresh_every: Ignored (included for compat with TV signature).
        inter_fetch_delay: Seconds between successive fetches. Default 0
            (unlimited API plan — no rate-limit throttle needed).
        on_progress: Optional callback ``(idx, total, symbol, exchange)``.
        max_workers: Thread pool size. Default 20.
        **kwargs: Ignored extra kwargs for compat.

    Returns:
        Dict mapping uppercase symbol to DataFrame (None for failed).
    """
    total = len(symbols)
    results: dict[str, pd.DataFrame] = {}
    t0 = time.perf_counter()
    ok_count = 0
    fail_count = 0

    def _fetch(sym: str) -> pd.DataFrame:
        return _fetch_aggs(sym, n_bars=n_bars)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures: dict[Any, str] = {}
        for symbol, _exchange in symbols:
            futures[ex.submit(_fetch, symbol)] = symbol.upper()

        idx = 0
        for future in as_completed(futures):
            sym_upper = futures[future]
            idx += 1
            try:
                df = future.result(timeout=30)
            except Exception as exc:
                logger.warning("Polygon batch fetch failed for %s: %s", sym_upper, exc)
                results[sym_upper] = None
                fail_count += 1
                continue

            if df is None or (hasattr(df, "empty") and df.empty):
                results[sym_upper] = None
                fail_count += 1
                continue

            results[sym_upper] = df
            ok_count += 1
            if on_progress is not None:
                on_progress(idx, total, sym_upper, "")

            if inter_fetch_delay > 0 and idx < total:
                time.sleep(inter_fetch_delay)

    logger.info(
        "Batch OHLCV done: %d/%d fetched, %d failed in %.1fs",
        ok_count, total, fail_count, time.perf_counter() - t0,
    )
    return results


def resolve_force_symbol(symbol: str) -> dict[str, Any]:
    """Resolve a symbol via Polygon Ticker Details.

    Returns a row dict with:
        name, symbol, exchange (MIC→short), market_cap, description, close.
    Returns None on failure.
    """
    client = _get_client()
    try:
        details = client.get_ticker_details(symbol)
        if details is None:
            logger.warning("Polygon: no ticker details for %s", symbol)
            return None

        mic = getattr(details, "primary_exchange", None)
        exchange = _mic_to_exchange(mic)

        return {
            "name": f"{exchange}:{symbol.upper()}",
            "symbol": symbol.upper(),
            "exchange": exchange,
            "market_cap": getattr(details, "market_cap", None),
            "description": getattr(details, "description", ""),
            "sic_description": getattr(details, "sic_description", ""),
            "close": getattr(details, "share_class_shares_outstanding", None),
        }
    except Exception as exc:
        logger.warning("Polygon: ticker details failed for %s: %s", symbol, exc)
        return None


# ── market snapshot (full-universe sweep) ───────────────────────


def fetch_market_snapshot() -> list[dict[str, Any]]:
    """Fetch the full US equities snapshot via Polygon Snapshot API.

    ``/v2/snapshot/locale/us/markets/stocks/tickers`` returns every actively
    traded US ticker in one response (no market cap). Returns rows:

        {symbol, exchange, price, dollar_volume_proxy, change_pct}

    ``price`` / ``dollar_volume_proxy`` come from the previous full-day bar
    (falling back to today's partial bar intraday). Exchange is a placeholder;
    the real exchange + market cap are resolved later via Ticker Details.
    """
    client = _get_client()
    try:
        snapshots = client.get_snapshot_all(market_type="stocks")
    except Exception as exc:
        logger.warning("Polygon market snapshot failed: %s", exc)
        return []

    rows: list[dict[str, Any]] = []
    for snap in snapshots:
        ticker = getattr(snap, "ticker", None)
        if not ticker:
            continue
        day = getattr(snap, "day", None)
        prev = getattr(snap, "prev_day", None)
        # Prefer the prior full-day bar for a stable after-close dollar-volume
        # estimate; fall back to today's (partial) bar during the session.
        ref = prev if prev is not None else day
        price: Optional[float] = None
        dollar_volume_proxy: Optional[float] = None
        if ref is not None:
            close = getattr(ref, "close", None)
            volume = getattr(ref, "volume", None)
            if close is not None:
                price = float(close)
            if close is not None and volume is not None:
                dollar_volume_proxy = float(close) * float(volume)
        rows.append({
            "symbol": str(ticker).upper(),
            "exchange": "NASDAQ",
            "price": price,
            "dollar_volume_proxy": dollar_volume_proxy,
            "change_pct": getattr(snap, "todays_change_percent", None),
        })
    logger.info("Polygon market snapshot: %d tickers", len(rows))
    return rows


def prefilter_snapshot(
    rows: list[dict[str, Any]],
    *,
    min_price: float = 10.0,
    min_dollar_vol: float = MIN_ADV_DOLLAR,
) -> list[dict[str, Any]]:
    """Trim snapshot rows by price and single-day dollar-volume proxy.

    Runs before the (expensive, per-symbol) market-cap resolution so only
    liquid, mid-to-large names reach Ticker Details.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        price = row.get("price")
        dollar_volume_proxy = row.get("dollar_volume_proxy")
        if price is None or dollar_volume_proxy is None:
            continue
        if float(price) < min_price:
            continue
        if float(dollar_volume_proxy) < min_dollar_vol:
            continue
        out.append(row)
    return out


def resolve_market_caps(
    symbols: list[str],
    *,
    min_mcap: float = MIN_MARKET_CAP,
    max_workers: int = 10,
) -> list[dict[str, Any]]:
    """Resolve market cap via Polygon Ticker Details for each symbol.

    Reuses ``resolve_force_symbol`` (one call per symbol); keeps only symbols
    with ``market_cap >= min_mcap``. Preserves input order.
    """
    if not symbols:
        return []

    def _resolve(symbol: str) -> Optional[dict[str, Any]]:
        details = resolve_force_symbol(symbol)
        if details is None:
            return None
        if passes_market_cap_gate(details.get("market_cap"), min_mcap=min_mcap):
            return details
        return None

    resolved: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for result in ex.map(_resolve, symbols):
            if result is not None:
                resolved.append(result)
    return resolved


def resolve_batch_details(
    symbols: list[str],
    *,
    max_workers: int = 10,
) -> dict[str, dict[str, Any]]:
    """Resolve Ticker Details for every symbol (no market-cap gate).

    Returns a ``{symbol: details}`` map for symbols that resolved; failed
    symbols are absent. Used by the premarket grep to attach name + SIC sector
    to capped snapshot survivors.
    """
    if not symbols:
        return {}

    def _resolve(symbol: str) -> tuple[str, Optional[dict[str, Any]]]:
        return symbol.upper(), resolve_force_symbol(symbol)

    details: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for symbol, result in ex.map(_resolve, symbols):
            if result is not None:
                details[symbol.upper()] = result
    return details


def to_ep_row(symbol: str, n_bars: int = 300, df: Optional[pd.DataFrame] = None) -> dict[str, Any]:
    """Build an EP-compatible row from Polygon daily bars.

    Ports the logic of ``enrich_from_ohlcv`` (tradingview.py:73) to 300 bars:
    - gap = (last_open - prior_close) / prior_close
    - rvol10 = last_volume / 10d_avg_volume
    - event_dollar_volume = close × volume of last bar
    - avg_dollar_volume_50d = mean(close × volume) over ~50 bars
    - market_cap = fetched from ticker details separately (caller provides)

    ``df`` may be passed to reuse an already-fetched OHLCV frame (avoids a
    second Polygon call when the EP technical feature test needs the bars).
    """
    if df is None:
        df = _fetch_aggs(symbol, n_bars=n_bars)
    if df is None or len(df) < 11:
        raise ValueError(f"Insufficient OHLCV for {symbol}")

    last = df.iloc[-1]
    prev = df.iloc[-2]
    open_price = float(last["open"])
    prior_close = float(prev["close"])
    close = float(last["close"])
    volume = float(last["volume"])

    # 10-day average volume (exclude last bar)
    hist = df.iloc[:-1]
    avg_vol_10 = float(hist["volume"].iloc[-10:].mean()) if len(hist) >= 10 else float(hist["volume"].mean())

    # 50-day average dollar volume (exclude last bar)
    window = hist.iloc[-50:] if len(hist) >= 50 else hist
    dollar_vol = (window["close"] * window["volume"]).astype(float)
    avg_dollar_50d = float(dollar_vol.mean()) if len(dollar_vol) else 0.0

    rvol10 = volume / avg_vol_10 if avg_vol_10 else 0.0
    gap = (open_price - prior_close) / prior_close * 100.0 if prior_close else 0.0
    event_dv = close * volume

    return {
        "name": f"POLYGON:{symbol.upper()}",
        "symbol": symbol.upper(),
        "exchange": "NASDAQ",
        "close": close,
        "open": open_price,
        "prior_close": prior_close,
        "gap": gap,
        "volume": volume,
        "relative_volume_10d_calc": rvol10,
        "Value.Traded": event_dv,
        "avg_dollar_volume_50d": avg_dollar_50d,
    }


def get_stock_data_dict(
    symbol: str,
    exchange: str = "NASDAQ",
    interval: str = "daily",
    n_bars: int = 300,
    **kwargs: Any,
) -> dict[str, Any]:
    """Return stock bars as a JSON-serializable dict (compat with ``tradingview_data``)."""
    df = _fetch_aggs(symbol, n_bars=n_bars)
    if df is None or df.empty:
        return {"symbol": symbol, "exchange": exchange, "interval": interval, "data": [], "summary": {}}

    data_records = []
    for idx, row in df.iterrows():
        data_records.append({
            "datetime": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })

    return {
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "data": data_records,
        "summary": {
            "total_bars": len(df),
            "date_range": {"start": str(df.index[0]), "end": str(df.index[-1])},
            "price_range": {"min": float(df["low"].min()), "max": float(df["high"].max())},
            "current_price": float(df["close"].iloc[-1]),
            "average_volume": float(df["volume"].mean()),
        },
    }


def get_stock_data_for_agent(
    symbol: str,
    exchange: str = "NASDAQ",
    interval: str = "daily",
    n_bars: int = 300,
    **kwargs: Any,
) -> str:
    """Return formatted string summary for agents (compat with ``tradingview_data``)."""
    df = _fetch_aggs(symbol, n_bars=n_bars)
    if df is None or df.empty:
        return f"No data for {symbol}"

    return (
        f"Stock Data for {symbol} on {exchange}\n"
        f"Interval: {interval}\n"
        f"Total bars: {len(df)}\n"
        f"Date range: {df.index[0]} to {df.index[-1]}\n"
        f"Current price: ${df['close'].iloc[-1]:.2f}\n"
        f"Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}\n"
        f"Average volume: {df['volume'].mean():,.0f}\n\n"
        f"Recent data (last 10 bars):\n"
        f"{df.tail(10).to_string()}\n\n"
        f"Full data available in DataFrame format."
    )


def fetch_spy() -> pd.DataFrame:
    """Fetch SPY daily OHLCV for benchmark/RS line computation."""
    df = _fetch_aggs("SPY", n_bars=300)
    if df is None or df.empty:
        logger.warning("SPY fetch from Polygon failed")
        return pd.DataFrame()
    return df


# ── pre-market minute bars ───────────────────────────────────────


def _premarket_window() -> tuple[str, str]:
    """Return (from_str, to_str) for today's pre-market window (ET) as Unix millis."""
    now_et = datetime.now(timezone.utc).astimezone(_EASTERN)
    today = now_et.date()
    start = datetime(today.year, today.month, today.day,
                     _PREMARKET_START_HOUR, _PREMARKET_START_MINUTE,
                     tzinfo=_EASTERN)
    end = datetime(today.year, today.month, today.day,
                   _PREMARKET_END_HOUR, _PREMARKET_END_MINUTE,
                   tzinfo=_EASTERN)
    return str(int(start.timestamp() * 1000)), str(int(end.timestamp() * 1000))


def fetch_premarket_aggs(symbol: str) -> pd.DataFrame:
    """Fetch 1-minute aggregates for *symbol* during today's pre-market window.

    Pre-market window: 4:00 AM – 9:30 AM Eastern.
    Returns a DataFrame with DatetimeIndex and columns open/high/low/close/volume.
    Returns an empty DataFrame on failure.
    """
    client = _get_client()
    from_str, to_str = _premarket_window()
    logger.info("Pre-market fetch for %s: %s → %s", symbol, from_str, to_str)
    t0 = time.perf_counter()

    try:
        aggs = client.get_aggs(
            ticker=symbol,
            multiplier=1,
            timespan="minute",
            from_=from_str,
            to=to_str,
            adjusted=False,
            limit=5000,
        )
        rows = [
            {
                "datetime": datetime.fromtimestamp(a.timestamp / 1000.0, tz=timezone.utc),
                "open": a.open,
                "high": a.high,
                "low": a.low,
                "close": a.close,
                "volume": a.volume,
            }
            for a in aggs
        ]
        if not rows:
            logger.info("Pre-market: no bars for %s (window %s → %s)", symbol, from_str, to_str)
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)
        elapsed_s = time.perf_counter() - t0
        logger.info("Pre-market %s: %d bars fetched in %.1fs", symbol, len(df), elapsed_s)
        return df

    except Exception as exc:
        logger.warning("Pre-market fetch failed for %s: %s", symbol, exc)
        return pd.DataFrame()


def get_premarket_data(symbol: str) -> dict[str, Any]:
    """Fetch pre-market summary for *symbol*.

    Returns a dict with:
        symbol, premarket_high, premarket_low, premarket_close
        (the last traded price in pre-market), premarket_volume,
        premarket_vwap (volume-weighted average price), bar_count.
    Empty values (0 or None) when no pre-market data.
    """
    df = fetch_premarket_aggs(symbol)
    if df.empty:
        return {
            "symbol": symbol.upper(),
            "premarket_high": None,
            "premarket_low": None,
            "premarket_close": None,
            "premarket_volume": 0,
            "premarket_vwap": None,
            "bar_count": 0,
        }
    vol = df["volume"].sum()
    if vol > 0:
        vwap = float((df["close"] * df["volume"]).sum() / vol)
    else:
        vwap = None
    return {
        "symbol": symbol.upper(),
        "premarket_high": float(df["high"].max()),
        "premarket_low": float(df["low"].min()),
        "premarket_close": float(df["close"].iloc[-1]),
        "premarket_volume": int(vol),
        "premarket_vwap": round(vwap, 4) if vwap is not None else None,
        "bar_count": len(df),
    }
