"""Seam: run_ep_scan builds dual-bucket JSON from a universe of rows."""

from datetime import date

from stock_analyze.scanners.ep.runner import run_ep_scan


def test_run_ep_scan_splits_baseline_and_strict_buckets():
    rows = [
        {
            "name": "NASDAQ:WEAK",
            "close": 5.0,
            "gap": 5.0,
            "relative_volume_10d_calc": 2.0,
            "market_cap_basic": 50_000_000,
            "Value.Traded": 1_000_000,
            "average_volume_60d_calc": 100_000,
        },
        {
            "name": "NASDAQ:STRONG",
            "close": 25.0,
            "gap": 9.0,
            "relative_volume_10d_calc": 4.0,
            "market_cap_basic": 800_000_000,
            "Value.Traded": 30_000_000,
            "average_volume_60d_calc": 400_000,
        },
    ]
    result = run_ep_scan(rows=rows, as_of=date(2026, 8, 8), universe_source="screener")

    assert result.baseline.count == 2
    assert {s.symbol for s in result.baseline.stocks} == {"WEAK", "STRONG"}
    assert result.strict.count == 1
    assert result.strict.stocks[0].symbol == "STRONG"
    assert "baseline" in result.gates
    assert "strict" in result.gates


def test_run_ep_scan_select_strict_omits_baseline_key():
    rows = [
        {
            "name": "NASDAQ:STRONG",
            "close": 25.0,
            "gap": 9.0,
            "relative_volume_10d_calc": 4.0,
            "market_cap_basic": 800_000_000,
            "Value.Traded": 30_000_000,
            "average_volume_60d_calc": 400_000,
        },
    ]
    result = run_ep_scan(rows=rows, as_of=date(2026, 8, 8))
    dumped = result.model_dump_selected("strict")
    assert "strict" in dumped
    assert "baseline" not in dumped


def test_force_included_symbol_flagged():
    rows = [
        {
            "name": "NYSE:FORCE",
            "close": 12.0,
            "gap": 8.5,
            "relative_volume_10d_calc": 3.2,
            "market_cap_basic": 500_000_000,
            "Value.Traded": 22_000_000,
            "average_volume_60d_calc": 500_000,
        },
    ]
    result = run_ep_scan(
        rows=rows,
        as_of=date(2026, 8, 8),
        force_symbols={("FORCE", "NYSE")},
        universe_source="hybrid",
    )
    assert result.strict.stocks[0].force_included is True
