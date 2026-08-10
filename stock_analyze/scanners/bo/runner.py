"""BO Agent 1 runner — screener→OHLCV→SPY→gate→detect→classify."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable, List, Mapping, Optional, Sequence, Set

import pandas as pd

from stock_analyze.data.symbols import SymbolKey, row_symbol_key
from stock_analyze.data.tradingview import get_stock_data
from stock_analyze.models.bo import BoScanBucket, BoSetupRating
from stock_analyze.scanners.bo.gates import passes_bo_gate
from stock_analyze.scanners.bo.metrics import score_bo_setup
from stock_analyze.scanners.vcp.gates import MIN_ADV_DOLLAR, passes_liquidity_gate

if TYPE_CHECKING:
    from stock_analyze.progress import RunProgress

logger = logging.getLogger(__name__)

ForceKey = SymbolKey
UniverseSource = str  # "screener" | "force" | "hybrid"


def merge_bo_force_rows(
    screener_rows: Iterable[Mapping[str, Any]],
    force_keys: Sequence[ForceKey],
    force_rows: Sequence[Mapping[str, Any]],
) -> tuple[List[dict[str, Any]], Set[ForceKey], UniverseSource]:
    """Merge screener + force-include rows; screener wins on duplicate.

    Returns (merged_rows, force_key_set, universe_source).
    """
    by_key: dict[ForceKey, dict[str, Any]] = {}
    screener_count = 0
    for row in screener_rows:
        screener_count += 1
        by_key[row_symbol_key(row)] = dict(row)

    for row in force_rows:
        key = row_symbol_key(row)
        if key not in by_key:
            by_key[key] = dict(row)

    force_set = {(s.upper(), e.upper()) for s, e in force_keys}
    if screener_count and force_set:
        source: UniverseSource = "hybrid"
    elif force_set:
        source = "force"
    else:
        source = "screener"

    return list(by_key.values()), force_set, source


def _fetch_spy() -> pd.DataFrame:
    """Fetch SPY daily OHLCV for RS line computation."""
    try:
        df = get_stock_data(
            symbol="SPY",
            exchange="AMEX",
            interval="daily",
            n_bars=300,
            return_format="dataframe",
        )
        return df
    except Exception:
        # Try NYSE fallback
        try:
            return get_stock_data(
                symbol="SPY", exchange="NYSE", interval="daily",
                n_bars=300, return_format="dataframe",
            )
        except Exception as exc:
            logger.warning("SPY fetch failed: %s", exc)
            return pd.DataFrame()


def run_bo_scan(
    screener_rows: List[dict[str, Any]],
    force_keys: Optional[Set[ForceKey]] = None,
    force_rows: Optional[List[dict[str, Any]]] = None,
    universe_source: UniverseSource = "screener",
    *,
    apply_gates: bool = True,
    n_bars: int = 300,
    batch_progress: Optional["RunProgress"] = None,
) -> BoScanBucket:
    """Run Qullamaggie BO structural scan on merged universe.

    When ``apply_gates`` is False, all stocks pass through (no BO gate
    filtering). Used for Manual "Run all pasted" mode.
    """
    merged, _, source = merge_bo_force_rows(
        screener_rows, force_keys or [], force_rows or [],
    )

    # Build symbol list for batch fetch
    symbols_to_fetch: list[tuple[str, str]] = []
    for row in merged:
        name = str(row.get("name") or "")
        symbol = str(row.get("symbol") or "")
        exchange = str(row.get("exchange") or "NASDAQ")
        if ":" in name and not symbol:
            parts = name.split(":", 1)
            exchange = parts[0].strip().upper()
            symbol = parts[1].strip().upper()
        if not symbol:
            continue
        symbols_to_fetch.append((symbol, exchange))

    logger.info("BO scan: fetching OHLCV for %d stocks", len(symbols_to_fetch))

    if batch_progress is not None:
        batch_progress.begin_ticker(
            len(symbols_to_fetch), "Batch OHLCV", throttle=5,
        )

    try:
        from tradingview_data import batch_get_stock_data

        ohlcv_map = batch_get_stock_data(
            symbols_to_fetch,
            n_bars=n_bars,
            refresh_every=50,
            inter_fetch_delay=0.3,
            on_progress=batch_progress.ticker if batch_progress is not None else None,
        )
    except ImportError:
        logger.warning("batch_get_stock_data not available, using single fetches")
        ohlcv_map = {}
        for sym, ex in symbols_to_fetch:
            try:
                df = get_stock_data(
                    symbol=sym, exchange=ex, interval="daily",
                    n_bars=n_bars, return_format="dataframe",
                )
                ohlcv_map[sym.upper()] = df
            except Exception as exc:
                logger.warning("OHLCV fetch failed for %s:%s: %s", ex, sym, exc)
                ohlcv_map[sym.upper()] = None
    finally:
        if batch_progress is not None:
            batch_progress.end_ticker()

    # Fetch SPY
    spy_df = _fetch_spy()

    # Run BO scoring
    ratings: list[BoSetupRating] = []
    for row in merged:
        name = str(row.get("name") or "")
        symbol = str(row.get("symbol") or "")
        exchange = str(row.get("exchange") or "NASDAQ")
        if ":" in name and not symbol:
            parts = name.split(":", 1)
            exchange = parts[0].strip().upper()
            symbol = parts[1].strip().upper()
        if not symbol:
            continue

        df = ohlcv_map.get(symbol.upper())
        if df is None or (hasattr(df, "empty") and df.empty):
            logger.warning("No OHLCV for %s:%s, skipping", exchange, symbol)
            continue

        # Liquidity gate — always enforced (even in "Run all pasted").
        if not passes_liquidity_gate(df):
            logger.debug(
                "Liquidity gate rejected %s (ADV$ < $%s)",
                symbol, f"{MIN_ADV_DOLLAR:,.0f}",
            )
            continue

        rating = score_bo_setup(df, spy_df, symbol=symbol, exchange=exchange)
        if rating is None:
            continue

        ratings.append(rating)

    # Classify into buckets
    five_star = [r for r in ratings if r.rating == 5]
    four_star = [r for r in ratings if r.rating == 4]
    three_star = [r for r in ratings if r.rating <= 3]

    # Apply BO gate filtering for passing stocks
    if apply_gates:
        passing = [r for r in ratings if passes_bo_gate(r)]
        five_star = [r for r in passing if r.rating == 5]
        four_star = [r for r in passing if r.rating == 4]
        three_star = [r for r in ratings if r.rating <= 3]
    else:
        passing = ratings

    return BoScanBucket(
        as_of=datetime.now(timezone.utc),
        universe_source=source,  # type: ignore[arg-type]
        gates_applied=apply_gates,
        ratings=ratings,
        five_star=five_star,
        four_star=four_star,
        three_star=three_star,
        count=len(ratings),
        counts={"5": len(five_star), "4": len(four_star), "3": len(three_star)},
    )
