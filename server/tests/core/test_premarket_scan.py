"""Seam: premarket runner (change% filter, cap, vol flag, strength tier)."""

from datetime import date

from stock_analyze.scanners.premarket.metrics import strength_tier, volume_flag
from stock_analyze.scanners.premarket.runner import (
    run_premarket_scan,
    select_premarket_candidates,
)


def _rows() -> list[dict]:
    return [
        {"symbol": "AAA", "exchange": "NASDAQ", "change_pct": 11.0, "price": 55.0,
         "volume": 5_000_000, "name": "Alpha", "sector": "Tech", "adv_20d": 1_000_000},
        {"symbol": "BBB", "exchange": "NASDAQ", "change_pct": 6.0, "price": 12.0,
         "volume": 1_000_000, "name": "Bravo", "sector": "Health", "adv_20d": 2_000_000},
        {"symbol": "CCC", "exchange": "NYSE", "change_pct": 4.0, "price": 30.0,
         "volume": 500_000, "name": "Charlie", "sector": "Energy", "adv_20d": 1_000_000},
        {"symbol": "DDD", "exchange": "NASDAQ", "change_pct": 12.0, "price": 8.0,
         "volume": 900_000, "name": "Delta", "sector": "Tech", "adv_20d": 300_000},
    ]


# ── metrics ───────────────────────────────────────────────────────


def test_strength_tier():
    assert strength_tier(10.0) == 5
    assert strength_tier(7.5) == 4
    assert strength_tier(5.0) == 3
    assert strength_tier(2.0) == 2


def test_volume_flag():
    assert volume_flag(5_000_000, 1_000_000, 3.0) is True
    assert volume_flag(2_000_000, 1_000_000, 3.0) is False
    assert volume_flag(None, 1_000_000, 3.0) is False
    assert volume_flag(5_000_000, 1_000_000, 0.0) is False  # flag off
    assert volume_flag(5_000_000, 0.0, 3.0) is False        # no ADV


# ── candidate selection ───────────────────────────────────────────


def test_select_candidates_filters_sorts_caps():
    candidates = select_premarket_candidates(
        _rows(), min_change_pct=5.0, cap=10, apply_gates=True,
    )
    assert [r["symbol"] for r in candidates] == ["DDD", "AAA", "BBB"]
    capped = select_premarket_candidates(_rows(), min_change_pct=0.0, cap=2, apply_gates=False)
    assert [r["symbol"] for r in capped] == ["DDD", "AAA"]


# ── runner ────────────────────────────────────────────────────────


def test_run_premarket_scan_gates_tiers_caps():
    bucket = run_premarket_scan(
        _rows(), as_of=date(2026, 8, 8), apply_gates=True,
        min_change_pct=5.0, min_vol_mult=0.0, cap=300,
    )
    assert [s.symbol for s in bucket.ratings] == ["DDD", "AAA", "BBB"]
    by_symbol = {s.symbol: s for s in bucket.ratings}
    assert by_symbol["DDD"].strength == 5
    assert by_symbol["AAA"].strength == 5
    assert by_symbol["BBB"].strength == 3
    assert all(s.vol_flag is False for s in bucket.ratings)
    assert bucket.count == 3


def test_run_premarket_scan_vol_flag():
    bucket = run_premarket_scan(
        _rows(), as_of=date(2026, 8, 8), apply_gates=True,
        min_change_pct=5.0, min_vol_mult=3.0, cap=300,
    )
    by_symbol = {s.symbol: s for s in bucket.ratings}
    assert by_symbol["AAA"].vol_flag is True   # 5M >= 3×1M
    assert by_symbol["BBB"].vol_flag is False  # 1M < 3×2M
    assert by_symbol["DDD"].vol_flag is True   # 900k >= 3×300k


def test_run_premarket_scan_cap_applies():
    bucket = run_premarket_scan(
        _rows(), as_of=date(2026, 8, 8), apply_gates=True,
        min_change_pct=5.0, min_vol_mult=0.0, cap=2,
    )
    assert [s.symbol for s in bucket.ratings] == ["DDD", "AAA"]


def test_run_premarket_scan_apply_gates_false_keeps_all():
    bucket = run_premarket_scan(
        _rows(), as_of=date(2026, 8, 8), apply_gates=False,
        min_change_pct=5.0, min_vol_mult=0.0, cap=300,
    )
    assert bucket.count == 4
    assert bucket.ratings[-1].symbol == "CCC"


def test_run_premarket_scan_force_rows_bypass_gate():
    rows = [
        {"symbol": "AAA", "exchange": "NASDAQ", "change_pct": 11.0},
        {"symbol": "ZZZ", "exchange": "NYSE", "change_pct": 1.0},
    ]
    bucket = run_premarket_scan(
        rows, as_of=date(2026, 8, 8), apply_gates=True,
        min_change_pct=5.0, min_vol_mult=0.0, cap=300,
        force_set={("ZZZ", "NYSE")},
    )
    assert {s.symbol for s in bucket.ratings} == {"AAA", "ZZZ"}
