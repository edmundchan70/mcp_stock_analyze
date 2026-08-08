"""Seam: Baseline / Strict gate predicates on EpStock metrics."""

from datetime import date

from stock_analyze.models.ep import EpStock
from stock_analyze.scanners.ep.gates import passes_baseline, passes_strict


def _stock(**overrides) -> EpStock:
    base = dict(
        symbol="TEST",
        exchange="NASDAQ",
        price=25.0,
        market_cap=800_000_000,
        avg_dollar_volume_50d=8_000_000,
        gap_pct=9.0,
        rvol10=3.5,
        event_dollar_volume=25_000_000,
        force_included=False,
        as_of=date(2026, 8, 8),
    )
    base.update(overrides)
    return EpStock(**base)


def test_baseline_passes_when_price_gap_and_rvol_meet_floors():
    assert passes_baseline(_stock(price=1.0, gap_pct=4.0, rvol10=1.5)) is True


def test_baseline_rejects_when_gap_below_four_percent():
    assert passes_baseline(_stock(gap_pct=3.99)) is False


def test_baseline_rejects_sub_dollar_price():
    assert passes_baseline(_stock(price=0.99, gap_pct=10.0, rvol10=5.0)) is False


def test_strict_passes_institutional_floors():
    assert passes_strict(_stock()) is True


def test_strict_rejects_when_market_cap_below_300m():
    assert passes_strict(_stock(market_cap=299_999_999)) is False


def test_strict_rejects_when_market_cap_above_10b():
    assert passes_strict(_stock(market_cap=10_000_000_001)) is False


def test_strict_rejects_when_event_dollar_volume_below_20m():
    assert passes_strict(_stock(event_dollar_volume=19_999_999)) is False


def test_stock_passing_baseline_may_fail_strict():
    stock = _stock(price=5.0, market_cap=None, avg_dollar_volume_50d=None, gap_pct=5.0, rvol10=2.0)
    assert passes_baseline(stock) is True
    assert passes_strict(stock) is False
