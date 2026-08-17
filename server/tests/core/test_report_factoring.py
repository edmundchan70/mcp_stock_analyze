"""Report factoring tests (T19): report_vcp / report_bo Agent-3 loops."""

from __future__ import annotations

from datetime import date

from stock_analyze.pipeline import report_bo, report_vcp


def _structural(symbol: str = "AAPL", rating: int = 5) -> dict:
    return {
        "symbol": symbol,
        "exchange": "NASDAQ",
        "structural_rating": rating,
        "structural_label": "textbook" if rating == 5 else "strong",
        "stage2_trend": True,
        "rs_rating": 85.0,
        "proximity_52w_pct": 95.0,
        "contraction_count": 3,
        "trough_symmetry_score": 5,
        "peak_symmetry_score": 5,
        "dollar_range_score": 5,
        "depth_score": 5,
        "tight_closes_score": 5,
        "volume_decay_score": 5,
        "time_contraction_score": 5,
        "as_of": str(date.today()),
    }


def _setup(symbol: str = "AAPL", rating: int = 5) -> dict:
    return {
        "symbol": symbol,
        "exchange": "NASDAQ",
        "variant": "classic",
        "rating": rating,
        "label": "textbook" if rating == 5 else "strong",
        "prior_impulse": True,
        "prior_impulse_pct": 50.0,
        "adr20": True,
        "adr20_pct": 6.0,
        "base_duration": True,
        "base_duration_days": 20,
        "vci": True,
        "vci_ratio": 0.52,
        "ma_stack": True,
        "surfing_dist_pct": 2.0,
        "pivot_kde": True,
        "higher_lows": True,
        "higher_lows_count": 2,
        "dryup": True,
        "dryup_ratio": 0.4,
        "volume_surge": True,
        "surge_pct": 320.0,
        "extension": False,
        "extension_pct": 0.0,
        "adv_20d": 60_000_000,
        "ema10_dist_pct": 3.0,
        "ema10_rising": True,
        "dryup_vol_ratio": 0.4,
        "tightness": 0.5,
        "q_base": 0,
        "funnel_stars": 0,
        "as_of": str(date.today()),
    }


def _context(symbol: str = "AAPL", *, leader: bool = True, flag: str = "HOT_SECTOR"):
    from stock_analyze.models.vcp import VcpContextEnrichment

    return VcpContextEnrichment(
        symbol=symbol,
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        industry_group_strength_flag=flag,
        is_category_leader=leader,
    )


def test_report_vcp_with_context_applies_caps():
    from stock_analyze.models.vcp import VcpStructuralRating

    stocks = [VcpStructuralRating(**_structural())]
    contexts = [_context()]  # leader + HOT_SECTOR → no cap
    rated = report_vcp(stocks, contexts)
    assert len(rated) == 1
    assert rated[0].final_rating == 5
    assert rated[0].cap_applied is False


def test_report_vcp_non_leader_capped():
    stocks = [_structural(rating=5)]
    contexts = [_context(leader=False)]  # non-leader 5★ → 4★
    rated = report_vcp(stocks, contexts)
    assert rated[0].final_rating == 4
    assert rated[0].cap_applied is True


def test_report_vcp_no_context_marks_no_enrichment():
    rated = report_vcp([_structural(rating=5)])
    assert len(rated) == 1
    # no context → never capped, flagged as no_enrichment
    assert rated[0].final_rating == 5
    assert rated[0].cap_applied is False
    assert rated[0].cap_reason == "no_enrichment"


def test_report_vcp_mixed_contexts_align_by_index():
    stocks = [_structural(symbol="AAPL", rating=5), _structural(symbol="MSFT", rating=5)]
    contexts = [_context("AAPL", leader=True), None]  # MSFT has no enrichment
    rated = report_vcp(stocks, contexts)
    by_symbol = {r.symbol: r for r in rated}
    assert by_symbol["AAPL"].cap_reason == ""
    assert by_symbol["MSFT"].cap_reason == "no_enrichment"


def test_report_vcp_sorts_by_rating_desc_then_symbol():
    stocks = [_structural(symbol="ZZ", rating=3), _structural(symbol="AA", rating=5)]
    rated = report_vcp(stocks)
    assert [r.symbol for r in rated] == ["AA", "ZZ"]


def test_report_bo_no_context_marks_no_enrichment():
    from stock_analyze.models.bo import BoSetupRating

    stocks = [BoSetupRating(**_setup(rating=5))]
    rated = report_bo(stocks)
    assert len(rated) == 1
    assert rated[0].final_rating == 5
    assert rated[0].cap_applied is False
    assert rated[0].cap_reason == "no_enrichment"


def test_report_bo_with_context_caps():
    from stock_analyze.models.bo import BoSetupRating

    stocks = [BoSetupRating(**_setup(rating=5))]
    rated = report_bo(stocks, [_context(leader=False)])
    assert rated[0].final_rating == 4
    assert rated[0].cap_applied is True
