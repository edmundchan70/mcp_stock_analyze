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

    by_symbol = {s.symbol: s for s in result.baseline.stocks}
    assert by_symbol["WEAK"].passes_baseline is True
    assert by_symbol["WEAK"].passes_strict is False
    assert by_symbol["STRONG"].passes_baseline is True
    assert by_symbol["STRONG"].passes_strict is True


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
        force_keys={("FORCE", "NYSE")},
        universe_source="hybrid",
    )
    assert result.strict.stocks[0].force_included is True


def test_apply_gates_false_keeps_failing_strict_names_in_both_buckets():
    """Run all pasted: skip gate predicates; every enriched stock is in both buckets."""
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
    result = run_ep_scan(
        rows=rows,
        as_of=date(2026, 8, 8),
        force_keys={("WEAK", "NASDAQ"), ("STRONG", "NASDAQ")},
        universe_source="force",
        apply_gates=False,
    )

    assert result.baseline.count == 2
    assert result.strict.count == 2
    assert {s.symbol for s in result.strict.stocks} == {"WEAK", "STRONG"}
    assert all(s.force_included for s in result.strict.stocks)


# ── EP technical feature mode ──────────────────────────────────────


_WEAK_ROW = {
    "name": "NASDAQ:WEAKTECH",
    "close": 0.5,
    "gap": 1.0,
    "relative_volume_10d_calc": 0.5,
    "market_cap_basic": 10_000_000,
    "Value.Traded": 100_000,
    "average_volume_60d_calc": 50_000,
}


def test_feature_mode_keeps_stock_gates_would_drop():
    """Feature test ON keeps a stock failing both gates when a feature holds."""
    from ep_fixtures import make_ep_textbook

    gated = run_ep_scan(rows=[_WEAK_ROW], as_of=date(2026, 8, 8))
    assert gated.baseline.count == 0
    assert gated.strict.count == 0

    df = make_ep_textbook()  # event volume 4x the quiet average → spike holds
    feature = run_ep_scan(
        rows=[_WEAK_ROW],
        as_of=date(2026, 8, 8),
        ep_features=True,
        ep_feature_keys=["volume_spike"],
        df_by_symbol={"WEAKTECH": df},
    )
    assert feature.baseline.count == 1
    assert feature.strict.count == 1
    stock = feature.baseline.stocks[0]
    assert stock.ep_keep is True
    assert stock.volume_spike is True
    assert stock.features_held >= 1


def test_feature_mode_gates_are_informational_only():
    """Feature survivors populate both buckets; gates never remove them.

    The gate outcomes are still evaluated and recorded per stock
    (``passes_baseline``/``passes_strict``) — informational, not filtering.
    """
    from ep_fixtures import make_ep_textbook, make_no_pullback_series

    hold_df = make_ep_textbook()          # spike + pullback both hold
    no_pull_df = make_no_pullback_series()  # spike holds, pullback fails

    feature = run_ep_scan(
        rows=[_WEAK_ROW],
        as_of=date(2026, 8, 8),
        ep_features=True,
        ep_feature_keys=["volume_spike", "pullback_contrast"],
        df_by_symbol={"WEAKTECH": hold_df},
    )
    assert feature.baseline.count == 1
    assert feature.strict.count == 1
    # Informational gates: the WEAK row fails both gates but the feature keeps it
    stock = feature.baseline.stocks[0]
    assert stock.ep_keep is True
    assert stock.passes_baseline is False
    assert stock.passes_strict is False

    keep_all = run_ep_scan(
        rows=[_WEAK_ROW],
        as_of=date(2026, 8, 8),
        ep_features=True,
        ep_feature_keys=["volume_spike", "pullback_contrast"],
        ep_keep_if_any=False,
        df_by_symbol={"WEAKTECH": no_pull_df},
    )
    assert keep_all.baseline.count == 0  # only spike holds → not every feature


def test_feature_mode_disabled_falls_back_to_gates():
    """All features off (empty key list) → feature mode inactive → gates apply."""
    from ep_fixtures import make_ep_textbook

    df = make_ep_textbook()
    result = run_ep_scan(
        rows=[_WEAK_ROW],
        as_of=date(2026, 8, 8),
        ep_features=True,
        ep_feature_keys=[],
        df_by_symbol={"WEAKTECH": df},
    )
    assert result.baseline.count == 0
    assert result.strict.count == 0
    assert result.baseline.stocks == []


def test_feature_mode_missing_ohlcv_drops_stock():
    """A symbol with no OHLCV frame gets all-False features → dropped."""
    from ep_fixtures import make_ep_textbook

    df = make_ep_textbook()
    rows = [
        dict(_WEAK_ROW, name="NASDAQ:WEAKTECH"),
        {"name": "NASDAQ:NODATA", "close": 30.0, "gap": 10.0, "relative_volume_10d_calc": 5.0},
    ]
    feature = run_ep_scan(
        rows=rows,
        as_of=date(2026, 8, 8),
        ep_features=True,
        ep_feature_keys=["volume_spike"],
        df_by_symbol={"WEAKTECH": df},
    )
    assert {s.symbol for s in feature.baseline.stocks} == {"WEAKTECH"}
