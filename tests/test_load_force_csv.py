"""Seam: force-include CSV loading."""

from pathlib import Path

from stock_analyze.scanners.ep.runner import load_force_csv


def test_load_force_csv_reads_symbol_and_exchange(tmp_path: Path):
    path = tmp_path / "force.csv"
    path.write_text("symbol,exchange\nAAPL,NASDAQ\nmsft,NYSE\n", encoding="utf-8")
    assert load_force_csv(str(path)) == [("AAPL", "NASDAQ"), ("MSFT", "NYSE")]
