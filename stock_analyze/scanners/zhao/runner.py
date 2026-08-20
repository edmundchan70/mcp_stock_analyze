"""照妖鏡 (zhao) Agent 1 runner — force-resolve → OHLCV → benchmark → gate → tier → rank."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Sequence

import pandas as pd

from stock_analyze.data.polygon import batch_get_stock_data, get_stock_data
from stock_analyze.models.zhao import (
    BENCHMARK,
    ZHAO_VARIANT,
    ZhaoScanBucket,
    ZhaoStock,
)
from stock_analyze.scanners.zhao.metrics import (
    pct_change,
    pct_from_high,
    rel_strength_20d,
    sma20,
    strength_tier_daily,
    strength_tier_realtime,
)

if TYPE_CHECKING:
    from stock_analyze.progress import RunProgress

logger = logging.getLogger(__name__)

StreakReader = Callable[[str], int]


def run_zhao_scan(
    rows: Sequence[Mapping[str, Any]],
    *,
    variant: ZHAO_VARIANT = "realtime",
    benchmark: BENCHMARK = "SPY",
    as_of: Optional[date] = None,
    apply_gates: bool = True,
    sma20_buffer_pct: float = 0.0,
    min_margin_pct: float = 1.0,
    min_rs_pct: float = 0.0,
    max_high_dist_pct: float = 15.0,
    n_bars: int = 300,
    streaks: Optional[Mapping[str, int]] = None,
    snapshot_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    batch_progress: Optional["RunProgress"] = None,
) -> ZhaoScanBucket:
    """Run the zhao scan over resolved force rows.

    Each input row must carry ``symbol`` + ``exchange`` (and may carry
    ``sic_description``/``market_cap`` from Polygon ticker details). OHLCV is
    batch-fetched per symbol; the benchmark OHLCV is fetched once.

    Keep rule per variant:
    - realtime: ``close > SMA20(1+buffer)`` AND ``margin_pct >= min_margin_pct``
      (margin = stock today% − benchmark today%), ranked by margin desc.
      ``today%`` comes from the market snapshot (``todaysChangePerc``, includes
      premarket) via ``snapshot_rows`` when supplied; otherwise the last daily
      close-to-close move is used.
    - daily: ``close > SMA20(1+buffer)`` AND ``rs_20d >= min_rs_pct`` AND
      ``pct_from_high >= -max_high_dist_pct``, ranked by rs_20d desc.

    ``streaks`` maps symbol → prior consecutive-day count (from scan_signals);
    a survivor's displayed streak is ``prior + 1``. ``apply_gates=False`` keeps
    every row that has enough OHLCV (streak still stamped).
    """
    day = as_of or datetime.now(timezone.utc).date()
    streak_map = dict(streaks or {})
    snapshot_pct: dict[str, float] = {}
    if snapshot_rows:
        for r in snapshot_rows:
            pct = r.get("change_pct")
            sym = str(r.get("symbol") or "").upper()
            if sym and pct is not None:
                snapshot_pct[sym] = float(pct)

    symbols_to_fetch: list[tuple[str, str]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "")
        exchange = str(row.get("exchange") or "NASDAQ")
        if not symbol:
            continue
        symbols_to_fetch.append((symbol, exchange))

    if not symbols_to_fetch:
        return ZhaoScanBucket(
            variant=variant,
            benchmark=benchmark,
            universe_source="force",
            gates_applied=apply_gates,
        )

    logger.info("zhao scan (%s): fetching OHLCV for %d stocks", variant, len(symbols_to_fetch))
    if batch_progress is not None:
        batch_progress.begin_ticker(len(symbols_to_fetch), "zhao OHLCV", throttle=5)
    ohlcv_map = batch_get_stock_data(
        symbols_to_fetch,
        n_bars=n_bars,
        on_progress=batch_progress.ticker if batch_progress is not None else None,
    )
    if batch_progress is not None:
        batch_progress.end_ticker()

    bench_df = get_stock_data(benchmark, n_bars=n_bars)

    stocks: list[ZhaoStock] = []
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        df = ohlcv_map.get(symbol.upper())
        if df is None or (hasattr(df, "empty") and df.empty):
            logger.warning("No OHLCV for %s, skipping", symbol)
            continue
        stock = _score_stock(
            row, df, bench_df,
            variant=variant,
            benchmark=benchmark,
            day=day,
            sma20_buffer_pct=sma20_buffer_pct,
            min_margin_pct=min_margin_pct,
            min_rs_pct=min_rs_pct,
            max_high_dist_pct=max_high_dist_pct,
            streak_prior=streak_map.get(symbol.upper(), 0),
            apply_gates=apply_gates,
            snapshot_pct=snapshot_pct if variant == "realtime" else None,
        )
        if stock is not None:
            stocks.append(stock)

    if variant == "daily":
        stocks.sort(key=lambda s: (s.rs_20d or 0.0), reverse=True)
    else:
        stocks.sort(key=lambda s: (s.margin_pct or 0.0), reverse=True)

    counts = {str(t): sum(1 for s in stocks if s.strength == t) for t in (5, 4, 3, 2)}
    return ZhaoScanBucket(
        as_of=day,
        universe_source="force",
        gates_applied=apply_gates,
        variant=variant,
        benchmark=benchmark,
        ratings=stocks,
        count=len(stocks),
        counts=counts,
    )


def _score_stock(
    row: Mapping[str, Any],
    df: pd.DataFrame,
    bench_df: pd.DataFrame,
    *,
    variant: ZHAO_VARIANT,
    benchmark: BENCHMARK,
    day: date,
    sma20_buffer_pct: float,
    min_margin_pct: float,
    min_rs_pct: float,
    max_high_dist_pct: float,
    streak_prior: int,
    apply_gates: bool,
    snapshot_pct: Optional[Mapping[str, float]] = None,
) -> Optional[ZhaoStock]:
    """Compute metrics + gates + strength tier for one symbol; None when gated out."""
    symbol = str(row.get("symbol") or "").upper()
    if len(df) < 21:
        return None

    close = float(df["close"].iloc[-1])
    prior_close = float(df["close"].iloc[-2])
    ma20 = sma20(df["close"])
    today_pct = pct_change(close, prior_close)

    bench_close = float(bench_df["close"].iloc[-1]) if len(bench_df) >= 2 else 0.0
    bench_prior = float(bench_df["close"].iloc[-2]) if len(bench_df) >= 2 else 0.0
    bench_pct = pct_change(bench_close, bench_prior)

    if snapshot_pct:
        # Realtime: prefer the snapshot's today's change % (includes premarket
        # activity) for both the stock and the benchmark; fall back to the
        # daily-bar close-to-close move when a symbol is missing from it.
        today_pct = snapshot_pct.get(symbol, today_pct)
        bench_pct = snapshot_pct.get(benchmark.upper(), bench_pct)

    margin_pct = today_pct - bench_pct
    rs_20d = rel_strength_20d(df["close"], bench_df["close"]) if len(bench_df) >= 21 else 0.0
    high_252 = float(df["high"].max())
    high_dist = pct_from_high(close, high_252)

    sector = str(row.get("sic_description") or row.get("sector") or "Unknown")
    exchange = str(row.get("exchange") or "NASDAQ")

    # ── gates ─────────────────────────────────────────────────────
    above_sma = close > ma20 * (1 + sma20_buffer_pct / 100.0)
    if apply_gates:
        if variant == "daily":
            if not (above_sma and rs_20d >= min_rs_pct and high_dist >= -max_high_dist_pct):
                return None
        else:  # realtime
            if not (above_sma and margin_pct >= min_margin_pct):
                return None

    if variant == "daily":
        strength = strength_tier_daily(rs_20d, high_dist)
    else:
        strength = strength_tier_realtime(margin_pct)

    return ZhaoStock(
        symbol=symbol,
        exchange=exchange,
        variant=variant,
        strength=strength,
        close=close,
        sma20=ma20,
        sector=sector,
        today_pct=today_pct,
        bench_pct=bench_pct,
        bench_symbol=benchmark,
        margin_pct=margin_pct,
        rs_20d=rs_20d,
        pct_from_high=high_dist,
        streak=streak_prior + 1,
        as_of=day,
    )


__all__ = ["StreakReader", "run_zhao_scan"]
