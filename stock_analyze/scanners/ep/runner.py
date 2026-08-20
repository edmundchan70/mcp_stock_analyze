"""EP Agent 1: merge universe → normalize → dual Baseline/Strict JSON."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence, Set

import pandas as pd

from stock_analyze.data.symbols import SymbolKey, row_symbol_key
from stock_analyze.models.ep import EpScanResult, EpStock, StockBucket
from stock_analyze.scanners.ep.gates import BASELINE, STRICT, passes_baseline, passes_strict
from stock_analyze.scanners.ep.metrics import normalize_row
from stock_analyze.scanners.ep.setup import (
    FEATURE_KEYS,
    EpSetupThresholds,
    score_ep_setup,
)

ForceKey = SymbolKey
UniverseSource = Literal["screener", "force", "hybrid"]


def run_ep_scan(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: Optional[date] = None,
    force_keys: Optional[Set[ForceKey]] = None,
    universe_source: UniverseSource = "screener",
    apply_gates: bool = True,
    ep_features: bool = False,
    ep_feature_keys: Optional[Sequence[str]] = None,
    ep_keep_if_any: bool = True,
    ep_thresholds: Optional[EpSetupThresholds] = None,
    df_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
) -> EpScanResult:
    """Filter normalized rows into baseline and strict buckets.

    When ``apply_gates`` is False, every successfully enriched stock is placed
    in both buckets (still marked ``force_included`` when in ``force_keys``).

    When the EP technical feature test is active (``ep_features`` AND at least
    one key in ``ep_feature_keys``), the Baseline/Strict gates become
    informational-only: the kept list is the feature survivors
    (``features_held >= 1`` with ``ep_keep_if_any``, or every enabled feature
    when ``ep_keep_if_any`` is False) and both buckets carry that same list.
    Each stock still records ``passes_baseline``/``passes_strict`` so the
    informational gate outcomes survive into the results.
    """
    day = as_of or datetime.now(timezone.utc).date()
    force = force_keys or set()
    force_upper = {(s.upper(), e.upper()) for s, e in force}

    feature_keys = list(ep_feature_keys or [])
    feature_mode = bool(ep_features) and len(feature_keys) > 0
    enabled = {k: k in feature_keys for k in FEATURE_KEYS}

    stocks: list[EpStock] = []
    for row in rows:
        try:
            stock = normalize_row(row, as_of=day, force_included=False)
        except (ValueError, TypeError):
            continue
        key = (stock.symbol.upper(), stock.exchange.upper())
        if key in force_upper:
            stock = stock.model_copy(update={"force_included": True})
        if feature_mode and df_by_symbol is not None:
            df = df_by_symbol.get(stock.symbol.upper())
            if df is not None and not (hasattr(df, "empty") and df.empty):
                features = score_ep_setup(
                    df,
                    enabled=enabled,
                    thresholds=ep_thresholds,
                    symbol=stock.symbol,
                    exchange=stock.exchange,
                    as_of=day,
                )
                if ep_keep_if_any:
                    ep_keep = features.features_held >= 1
                else:
                    ep_keep = (
                        features.features_held == len(feature_keys)
                        if feature_keys
                        else False
                    )
                stock = stock.model_copy(
                    update={
                        "event_idx": features.event_idx,
                        "base_detected": features.base_detected,
                        "volume_spike": features.volume_spike,
                        "pullback_contrast": features.pullback_contrast,
                        "ema_support": features.ema_support,
                        "vwap_support": features.vwap_support,
                        "features_held": features.features_held,
                        "ep_keep": ep_keep,
                    }
                )
        stock = stock.model_copy(
            update={
                "passes_baseline": passes_baseline(stock),
                "passes_strict": passes_strict(stock),
            }
        )
        stocks.append(stock)

    if feature_mode:
        baseline_stocks = [s for s in stocks if s.ep_keep]
        strict_stocks = baseline_stocks
    elif apply_gates:
        baseline_stocks = [s for s in stocks if passes_baseline(s)]
        strict_stocks = [s for s in stocks if passes_strict(s)]
    else:
        baseline_stocks = list(stocks)
        strict_stocks = list(stocks)

    return EpScanResult(
        as_of=datetime.now(timezone.utc),
        universe_source=universe_source,
        session="rth",
        gates={"baseline": BASELINE, "strict": STRICT},
        baseline=StockBucket(count=len(baseline_stocks), stocks=baseline_stocks),
        strict=StockBucket(count=len(strict_stocks), stocks=strict_stocks),
    )


def merge_force_rows(
    screener_rows: Iterable[Mapping[str, Any]],
    force_keys: Sequence[ForceKey],
    force_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Set[ForceKey], UniverseSource]:
    """Merge screener + force-include rows; prefer screener row when duplicate."""
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
