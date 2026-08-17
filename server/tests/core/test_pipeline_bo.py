"""Unit tests for BO pipeline orchestration."""

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from stock_analyze.pipeline import (
    RunConfig,
    execute_bo_enrichment,
    execute_bo_scan,
    format_bo_near_miss_table,
    format_bo_rating_table,
    run_daily,
    sanitize_run_name,
    strip_internal_keys,
)


def _make_rating_dict(rating: int = 5, symbol: str = "AAPL") -> dict:
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


class TestRunConfig:
    def test_run_config_bo_pipeline_type(self):
        cfg = RunConfig(name="test", pipeline_type="daily_bo_scan", force_keys=[("AAPL", "NASDAQ")])
        assert cfg.pipeline_type == "daily_bo_scan"


class TestExecuteBoScan:
    @patch("stock_analyze.pipeline.resolve_force_symbol")
    @patch("stock_analyze.pipeline.run_bo_scan")
    def test_execute_bo_scan_writes_payload(self, mock_scan, mock_resolve):
        mock_resolve.return_value = {
            "name": "NASDAQ:AAPL", "symbol": "AAPL", "exchange": "NASDAQ",
            "market_cap": 800_000_000, "description": "Apple Inc.",
        }
        from stock_analyze.models.bo import BoScanBucket

        mock_scan.return_value = BoScanBucket(counts={"5": 1, "4": 2, "3": 0}, count=3)

        result = execute_bo_scan(
            force_keys=[("AAPL", "NASDAQ")],
            limit=300,
            apply_gates=True,
        )
        assert "_counts" in result
        assert result["_counts"]["5"] == 1

    @patch("stock_analyze.pipeline.run_bo_scan")
    def test_execute_bo_scan_no_screener(self, mock_scan):
        from stock_analyze.models.bo import BoScanBucket

        mock_scan.return_value = BoScanBucket(counts={"5": 0, "4": 0, "3": 0}, count=0)

        with pytest.raises(ValueError, match="force_keys"):
            execute_bo_scan(limit=300, use_screener=False, apply_gates=True)

    @patch("stock_analyze.pipeline.run_bo_scan")
    def test_execute_bo_scan_requires_force_keys(self, mock_scan):
        with pytest.raises(ValueError, match="force_keys"):
            execute_bo_scan(limit=300, apply_gates=True)


class TestExecuteBoSweep:
    @patch("stock_analyze.pipeline.run_bo_scan")
    @patch("stock_analyze.pipeline.resolve_market_caps")
    @patch("stock_analyze.pipeline.prefilter_snapshot")
    @patch("stock_analyze.pipeline.fetch_market_snapshot")
    def test_execute_bo_scan_sweep(self, mock_snapshot, mock_prefilter, mock_resolve, mock_scan):
        from stock_analyze.models.bo import BoScanBucket

        snap = [{"symbol": "AAPL", "price": 150.0, "dollar_volume_proxy": 1_000_000_000}]
        mock_snapshot.return_value = snap
        mock_prefilter.return_value = snap
        mock_resolve.return_value = [
            {"name": "NASDAQ:AAPL", "symbol": "AAPL", "exchange": "NASDAQ", "market_cap": 800_000_000}
        ]
        mock_scan.return_value = BoScanBucket(counts={"5": 1, "4": 0, "3": 0}, count=1)

        result = execute_bo_scan(use_screener=True, apply_gates=True)

        assert result["_counts"]["5"] == 1
        mock_scan.assert_called_once()
        kwargs = mock_scan.call_args.kwargs
        assert kwargs["universe_source"] == "snapshot"
        assert kwargs["force_keys"] == set()
        assert kwargs["force_rows"] == []


class TestExecuteBoEnrichment:
    @patch("stock_analyze.pipeline.enrich_with_vcp_context")
    def test_execute_bo_enrichment(self, mock_enrich):
        from stock_analyze.models.bo import BoSetupRating
        from stock_analyze.models.vcp import VcpContextEnrichment

        setup = BoSetupRating(**_make_rating_dict(rating=5))

        mock_enrich.return_value = [
            VcpContextEnrichment(
                symbol="AAPL", exchange="NASDAQ",
                sector="Technology", industry="Consumer Electronics",
                industry_group_strength_flag="HOT_SECTOR",
                is_category_leader=True,
            )
        ]

        result = execute_bo_enrichment([setup])
        assert "agent2" in result
        assert "agent3" in result
        assert len(result["rated_stocks"]) == 1
        assert result["rated_stocks"][0].final_rating == 5

    @patch("stock_analyze.pipeline.enrich_with_vcp_context")
    def test_execute_bo_enrichment_skips_empty(self, mock_enrich):
        mock_enrich.return_value = []
        result = execute_bo_enrichment([])
        assert len(result["rated_stocks"]) == 0


class TestFormatBoRatingTable:
    def test_format_bo_rating_table(self):
        from stock_analyze.models.bo import BoRatedStock

        stock = BoRatedStock(
            symbol="AAPL", exchange="NASDAQ",
            setup_rating=5, setup_label="textbook",
            variant="classic", as_of=date.today(),
            final_rating=5, final_label="textbook",
        )
        table = format_bo_rating_table([stock], min_rating=4)
        assert "AAPL" in table
        assert "5★" in table

    def test_format_bo_rating_table_empty(self):
        assert format_bo_rating_table([], min_rating=4) == "(no names at this min-rating)"


class TestRunDailyBo:
    @patch("stock_analyze.pipeline.execute_bo_scan")
    @patch("stock_analyze.pipeline.execute_bo_enrichment")
    def test_run_daily_dispatches_bo_pipeline(self, mock_enrich, mock_scan):
        """pipeline_type=daily_bo_scan → calls BO path."""
        from stock_analyze.models.bo import BoRatedStock

        mock_scan.return_value = {
            "ratings": [_make_rating_dict(rating=5)],
            "five_star": [_make_rating_dict(rating=5)],
            "four_star": [], "three_star": [],
            "_counts": {"5": 1, "4": 0, "3": 0},
            "count": 1,
            "counts": {"5": 1, "4": 0, "3": 0},
            "gates_applied": True,
        }

        mock_enrich.return_value = {
            "agent2": {"count": 1, "stocks": []},
            "agent3": {"count": 1, "stocks": []},
            "rated_stocks": [
                BoRatedStock(
                    symbol="AAPL", exchange="NASDAQ",
                    setup_rating=5, setup_label="textbook",
                    variant="classic", as_of=date.today(),
                    final_rating=5, final_label="textbook",
                )
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = RunConfig(
                name="bo-test",
                pipeline_type="daily_bo_scan",
                output_root=Path(tmpdir),
                run_catalyst=True,
                force_keys=[("AAPL", "NASDAQ")],
            )
            result = run_daily(cfg)
            assert result.exit_code == 0
            assert "agent1" in result.steps_completed
            assert "agent3" in result.steps_completed

    @patch("stock_analyze.pipeline.execute_bo_scan")
    def test_run_daily_bo_no_survivor_prints_near_miss(self, mock_scan):
        """no funnel survivors → short-circuit with only agent1, exit 0."""
        mock_scan.return_value = {
            "ratings": [_make_rating_dict(rating=3, symbol="TEST")],
            "five_star": [], "four_star": [],
            "three_star": [_make_rating_dict(rating=3, symbol="TEST")],
            "near_miss": [
                {
                    "symbol": "TEST",
                    "exchange": "NYSE",
                    "variant": "classic",
                    "rating": 3,
                    "passed_essentials": [
                        "prior_impulse", "adr20", "base_duration", "vci",
                        "ma_stack", "pivot_kde", "higher_lows", "dryup",
                    ],
                    "failed_essentials": ["volume_surge"],
                    "passed_count": 8,
                    "failed_count": 1,
                    "dryup_ratio": 0.4,
                    "surge_pct": 120.0,
                    "surfing_dist_pct": 2.0,
                    "pivot": 150.0,
                    "breakout_date": None,
                    "rvol10": 0.0,
                    "rs_rating": 85.0,
                }
            ],
            "_counts": {"5": 0, "4": 0, "3": 1},
            "count": 1,
            "counts": {"5": 0, "4": 0, "3": 1},
            "gates_applied": True,
        }
        # Ratings lack funnel fields → funnel rejects all
        mock_scan.return_value["ratings"][0].update({
            "adv_20d": 10_000_000,  # below floor
            "ema10_dist_pct": 999.0,
            "ema10_rising": False,
            "dryup_vol_ratio": 5.0,
            "tightness": 999.0,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = RunConfig(
                name="bo-nosurvivor",
                pipeline_type="daily_bo_scan",
                output_root=Path(tmpdir),
                run_catalyst=True,
                force_keys=[("TEST", "NYSE")],
            )
            result = run_daily(cfg)
            assert result.exit_code == 0
            assert result.steps_completed == ["agent1"]


class TestExecuteBoScanNearMiss:
    @patch("stock_analyze.pipeline.resolve_force_symbol")
    @patch("stock_analyze.pipeline.run_bo_scan")
    def test_execute_bo_scan_payload_has_near_miss(self, mock_scan, mock_resolve):
        """BO scan payload carries near_miss that survives strip_internal_keys."""
        mock_resolve.return_value = {
            "name": "NASDAQ:AAPL", "symbol": "AAPL", "exchange": "NASDAQ",
            "market_cap": 800_000_000, "description": "Apple Inc.",
        }
        from stock_analyze.models.bo import BoNearMiss, BoScanBucket

        nm = BoNearMiss(
            symbol="AAPL", exchange="NASDAQ", variant="classic",
            passed_essentials=["prior_impulse", "adr20", "base_duration", "vci",
                               "ma_stack", "pivot_kde", "higher_lows", "dryup"],
            failed_essentials=["volume_surge"],
            passed_count=8, failed_count=1,
        )
        bucket = BoScanBucket(
            counts={"5": 0, "4": 0, "3": 1}, count=1,
            near_miss=[nm],
        )
        mock_scan.return_value = bucket

        result = execute_bo_scan(
            force_keys=[("AAPL", "NASDAQ")],
            limit=300,
            apply_gates=True,
        )
        assert "near_miss" in result
        assert len(result["near_miss"]) == 1

        stripped = strip_internal_keys(result)
        assert "near_miss" in stripped
        assert "_counts" not in stripped


class TestFormatBoNearMissTable:
    def test_format_near_miss_table_empty(self):
        assert format_bo_near_miss_table([]) == "(no near-miss stocks)"

    def test_format_near_miss_table_with_data(self):
        near = [
            {
                "symbol": "TEST",
                "variant": "classic",
                "failed_essentials": ["volume_surge"],
                "rs_rating": 85.0,
                "surge_pct": 120.0,
            }
        ]
        table = format_bo_near_miss_table(near)
        assert "TEST" in table
        assert "volume_surge" in table


class TestWizardWording:
    def test_apply_gate_wording_bo_vs_ep(self):
        """BO/VCP (structural=True) → 'funnel gate'; EP (structural=False) → 'Baseline/Strict'."""
        from unittest.mock import patch
        from stock_analyze.interactive import _prompt_apply_gate_or_run_all

        with patch("stock_analyze.interactive._select") as mock_select:
            mock_select.return_value = "apply"
            _prompt_apply_gate_or_run_all(structural=True)
            choices = mock_select.call_args[0][1]
            structural_label = choices[0].title
            assert "funnel gate" in structural_label.lower()

            _prompt_apply_gate_or_run_all(structural=False)
            choices2 = mock_select.call_args[0][1]
            ep_label = choices2[0].title
            assert "Baseline/Strict" in ep_label
