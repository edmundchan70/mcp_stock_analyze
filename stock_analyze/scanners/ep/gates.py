"""Baseline and Strict gate thresholds and predicates."""

from stock_analyze.models.ep import EpStock, GateThresholds

BASELINE = GateThresholds(
    min_price=1.0,
    min_gap_pct=4.0,
    min_rvol10=1.5,
)

STRICT = GateThresholds(
    min_price=10.0,
    min_gap_pct=8.0,
    min_rvol10=3.0,
    min_market_cap=300_000_000,
    max_market_cap=10_000_000_000,
    min_avg_dollar_volume_50d=5_000_000,
    min_event_dollar_volume=20_000_000,
)


def passes_baseline(stock: EpStock, thresholds: GateThresholds = BASELINE) -> bool:
    return (
        stock.price >= thresholds.min_price
        and stock.gap_pct >= thresholds.min_gap_pct
        and stock.rvol10 >= thresholds.min_rvol10
    )


def passes_strict(stock: EpStock, thresholds: GateThresholds = STRICT) -> bool:
    if not (
        stock.price >= thresholds.min_price
        and stock.gap_pct >= thresholds.min_gap_pct
        and stock.rvol10 >= thresholds.min_rvol10
    ):
        return False
    if thresholds.min_market_cap is not None:
        if stock.market_cap is None or stock.market_cap < thresholds.min_market_cap:
            return False
    if thresholds.max_market_cap is not None:
        if stock.market_cap is None or stock.market_cap > thresholds.max_market_cap:
            return False
    if thresholds.min_avg_dollar_volume_50d is not None:
        if (
            stock.avg_dollar_volume_50d is None
            or stock.avg_dollar_volume_50d < thresholds.min_avg_dollar_volume_50d
        ):
            return False
    if thresholds.min_event_dollar_volume is not None:
        if (
            stock.event_dollar_volume is None
            or stock.event_dollar_volume < thresholds.min_event_dollar_volume
        ):
            return False
    return True
