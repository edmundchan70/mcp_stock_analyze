"""Seam: zhao metrics + runner (realtime margin gate, daily RS ranking, streak)."""

from datetime import date

import pandas as pd

from stock_analyze.scanners.zhao.metrics import (
    pct_change,
    pct_from_high,
    rel_strength_20d,
    sma20,
    strength_tier_daily,
    strength_tier_realtime,
)
from stock_analyze.scanners.zhao.runner import run_zhao_scan


def _frame(closes: list[float], highs: list[float] | None = None) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "open": list(closes),
            "high": highs or [c * 1.02 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": list(closes),
            "volume": [1_000_000] * n,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


# ── metrics ───────────────────────────────────────────────────────


def test_sma20_trailing_mean():
    closes = [float(i) for i in range(1, 31)]
    assert abs(sma20(closes) - 20.5) < 1e-9


def test_pct_change():
    assert abs(pct_change(110.0, 100.0) - 10.0) < 1e-9
    assert pct_change(100.0, 0.0) == 0.0


def test_rel_strength_20d_outperforms():
    stock = [100.0] * 20 + [110.0]      # +10% over 20d
    bench = [100.0] * 20 + [105.0]      # +5%
    rs = rel_strength_20d(stock, bench)
    assert abs(rs - 5.0) < 1e-9


def test_rel_strength_20d_short_series_zero():
    assert rel_strength_20d([1, 2, 3], [1, 2, 3]) == 0.0


def test_pct_from_high_negative_below_high():
    assert abs(pct_from_high(85.0, 100.0) - (-15.0)) < 1e-9
    assert abs(pct_from_high(100.0, 100.0)) < 1e-9
    assert pct_from_high(10.0, 0.0) == 0.0


def test_strength_tiers():
    assert strength_tier_realtime(3.0) == 5
    assert strength_tier_realtime(1.5) == 4
    assert strength_tier_realtime(0.4) == 3
    assert strength_tier_realtime(-2.0) == 2

    assert strength_tier_daily(12.0, -3.0) == 5
    assert strength_tier_daily(6.0, -8.0) == 4
    assert strength_tier_daily(1.0, -12.0) == 3
    assert strength_tier_daily(-5.0, -20.0) == 2


# ── runner: realtime ──────────────────────────────────────────────


def _realtime_rows(monkeypatch):
    def _batch(symbols, n_bars=300, on_progress=None):
        return {
            # AAA: today flat (margin -1.0 vs SPY +1.0) → gated out
            "AAA": _frame([99.0] * 24 + [100.0, 100.0]),
            # BBB: +3% today, margin +2.0 → tier 4
            "BBB": _frame([90.0] * 24 + [100.0, 103.0]),
            # CCC: +4% today, margin +3.0 → tier 5
            "CCC": _frame([90.0] * 24 + [100.0, 104.0]),
            # DDD: flat, close == sma20 → fails above-sma gate
            "DDD": _frame([50.0] * 24 + [50.0, 50.0]),
        }
    monkeypatch.setattr(
        "stock_analyze.scanners.zhao.runner.batch_get_stock_data", _batch,
    )
    monkeypatch.setattr(
        "stock_analyze.scanners.zhao.runner.get_stock_data",
        lambda sym, n_bars=300: _frame([100.0] * 24 + [100.0, 101.0]),  # SPY +1.0%
    )


def test_run_zhao_scan_realtime_gates_and_tiers(monkeypatch):
    _realtime_rows(monkeypatch)
    rows = [
        {"symbol": "AAA", "exchange": "NASDAQ", "sic_description": "Software"},
        {"symbol": "BBB", "exchange": "NASDAQ", "sic_description": "Software"},
        {"symbol": "CCC", "exchange": "NASDAQ", "sic_description": "Hardware"},
        {"symbol": "DDD", "exchange": "NASDAQ", "sic_description": "Hardware"},
    ]
    bucket = run_zhao_scan(
        rows, variant="realtime", benchmark="SPY",
        as_of=date(2026, 8, 8), apply_gates=True, min_margin_pct=1.0,
    )
    symbols = [s.symbol for s in bucket.ratings]
    # DDD flat is gated out; margin AAA=-0.0 fails >=1.0.
    assert "DDD" not in symbols
    assert symbols == ["CCC", "BBB"]  # ranked by margin desc
    by_symbol = {s.symbol: s for s in bucket.ratings}
    assert by_symbol["CCC"].strength == 5   # margin 3.0
    assert by_symbol["BBB"].strength == 4   # margin 2.0
    assert abs(by_symbol["BBB"].margin_pct - 2.0) < 1e-9
    assert bucket.gates_applied is True


def test_run_zhao_scan_realtime_apply_gates_false_keeps_all(monkeypatch):
    _realtime_rows(monkeypatch)
    rows = [{"symbol": "DDD", "exchange": "NASDAQ", "sic_description": "X"}]
    bucket = run_zhao_scan(
        rows, variant="realtime", benchmark="SPY",
        as_of=date(2026, 8, 8), apply_gates=False,
    )
    assert [s.symbol for s in bucket.ratings] == ["DDD"]
    assert bucket.ratings[0].strength == 2


def test_run_zhao_scan_realtime_uses_snapshot_today_pct(monkeypatch):
    """Realtime today% comes from the market snapshot (todaysChangePerc, which
    includes premarket), not the last daily close-to-close bar."""
    _realtime_rows(monkeypatch)  # BBB's last bar is +3%; snapshot says +7%
    rows = [{"symbol": "BBB", "exchange": "NASDAQ", "sic_description": "Software"}]
    bucket = run_zhao_scan(
        rows, variant="realtime", benchmark="SPY",
        as_of=date(2026, 8, 8), apply_gates=True, min_margin_pct=1.0,
        snapshot_rows=[
            {"symbol": "BBB", "change_pct": 7.0},   # vs SPY +1.0 → margin 6.0
            {"symbol": "SPY", "change_pct": 1.0},
        ],
    )
    assert [s.symbol for s in bucket.ratings] == ["BBB"]
    stock = bucket.ratings[0]
    assert abs(stock.today_pct - 7.0) < 1e-9
    assert abs(stock.bench_pct - 1.0) < 1e-9
    assert abs(stock.margin_pct - 6.0) < 1e-9
    assert stock.strength == 5   # margin 6.0 >= 3.0


# ── runner: daily ─────────────────────────────────────────────────


def _daily_rows(monkeypatch):
    # bench flat → rs_20d equals the stock's trailing-20 return.
    bench_closes = [100.0] * 26                          # flat

    def _batch(symbols, n_bars=300, on_progress=None):
        return {
            # +5% over trailing 20; close > trailing sma20
            "AAA": _frame([100.0] * 5 + [104.0] * 19 + [105.0]),
            # +10% over trailing 20; close > trailing sma20
            "BBB": _frame([100.0] * 5 + [109.5] * 19 + [110.0]),
        }
    monkeypatch.setattr(
        "stock_analyze.scanners.zhao.runner.batch_get_stock_data", _batch,
    )
    monkeypatch.setattr(
        "stock_analyze.scanners.zhao.runner.get_stock_data",
        lambda sym, n_bars=300: _frame(bench_closes),
    )


def test_run_zhao_scan_daily_rs_ranking_and_streak(monkeypatch):
    _daily_rows(monkeypatch)
    rows = [
        {"symbol": "AAA", "exchange": "NASDAQ", "sic_description": "A"},
        {"symbol": "BBB", "exchange": "NASDAQ", "sic_description": "B"},
    ]
    bucket = run_zhao_scan(
        rows, variant="daily", benchmark="SPY",
        as_of=date(2026, 8, 8), apply_gates=True,
        min_rs_pct=0.0, max_high_dist_pct=15.0,
        streaks={"BBB": 2},
    )
    symbols = [s.symbol for s in bucket.ratings]
    assert symbols == ["BBB", "AAA"]  # ranked by rs desc
    by_symbol = {s.symbol: s for s in bucket.ratings}
    assert by_symbol["BBB"].strength == 5       # rs 10, high_dist ~0
    assert by_symbol["AAA"].strength == 4       # rs 5, high_dist ~0
    assert by_symbol["BBB"].streak == 3         # prior 2 + today
    assert by_symbol["AAA"].streak == 1
    assert bucket.variant == "daily"


def test_run_zhao_scan_daily_gates_on_high_dist(monkeypatch):
    def _batch(symbols, n_bars=300, on_progress=None):
        # close far below the 252d high (highs = +80% above close)
        return {"AAA": _frame([100.0] * 25, highs=[180.0] * 25)}
    monkeypatch.setattr(
        "stock_analyze.scanners.zhao.runner.batch_get_stock_data", _batch,
    )
    monkeypatch.setattr(
        "stock_analyze.scanners.zhao.runner.get_stock_data",
        lambda sym, n_bars=300: _frame([100.0] * 25),
    )
    rows = [{"symbol": "AAA", "exchange": "NASDAQ", "sic_description": "A"}]
    bucket = run_zhao_scan(
        rows, variant="daily", benchmark="SPY",
        as_of=date(2026, 8, 8), apply_gates=True,
        min_rs_pct=0.0, max_high_dist_pct=15.0,
    )
    assert bucket.ratings == []  # pct_from_high ≈ -44.4% < -15


def test_run_zhao_scan_empty_rows_returns_empty_bucket(monkeypatch):
    bucket = run_zhao_scan(
        [], variant="realtime", benchmark="SPY", as_of=date(2026, 8, 8),
    )
    assert bucket.ratings == []
    assert bucket.count == 0
