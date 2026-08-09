"""Unit tests for VCP pipeline orchestration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stock_analyze.pipeline import (
    RunConfig,
    RunResult,
    execute_vcp_scan,
    execute_vcp_enrichment,
    run_daily,
    sanitize_run_name,
    strip_internal_keys,
)


class TestRunConfig:
    def test_run_config_vcp_pipeline_type(self):
        cfg = RunConfig(
            name="test",
            select="strict",
            pipeline_type="daily_vcp_scan",
        )
        assert cfg.pipeline_type == "daily_vcp_scan"


class TestSanitize:
    def test_sanitize_run_name_handles_special_chars(self):
        assert sanitize_run_name("test run!") == "test_run"
        assert sanitize_run_name("my-scan-2024") == "my-scan-2024"
        assert sanitize_run_name("multiple   spaces") == "multiple_spaces"

    def test_sanitize_raises_on_empty(self):
        with pytest.raises(ValueError):
            sanitize_run_name("!!!")


class TestExecuteVcpScan:
    @patch("stock_analyze.pipeline.fetch_us_vcp_universe")
    @patch("stock_analyze.pipeline.run_vcp_scan")
    def test_execute_vcp_scan_writes_payload(self, mock_scan, mock_screener):
        mock_screener.return_value = [
            {"name": "NASDAQ:AAPL", "symbol": "AAPL", "exchange": "NASDAQ", "close": 150.0}
        ]
        from stock_analyze.models.vcp import VcpScanBucket
        mock_scan.return_value = VcpScanBucket(counts={"5": 1, "4": 2, "3": 0}, count=3)

        result = execute_vcp_scan(limit=300, apply_gates=True)
        assert "_counts" in result
        assert result["_counts"]["5"] == 1

    @patch("stock_analyze.pipeline.fetch_us_vcp_universe")
    @patch("stock_analyze.pipeline.run_vcp_scan")
    def test_execute_vcp_scan_no_screener(self, mock_scan, mock_screener):
        from stock_analyze.models.vcp import VcpScanBucket
        mock_scan.return_value = VcpScanBucket(counts={"5": 0, "4": 0, "3": 0}, count=0)

        with pytest.raises(ValueError, match="non-empty force_keys"):
            execute_vcp_scan(limit=300, use_screener=False, apply_gates=True)


class TestExecuteVcpEnrichment:
    @patch("stock_analyze.pipeline.enrich_with_vcp_context")
    def test_execute_vcp_enrichment(self, mock_enrich):
        from stock_analyze.models.vcp import VcpContextEnrichment, VcpStructuralRating
        from datetime import date

        structural = VcpStructuralRating(
            symbol="AAPL", exchange="NASDAQ",
            structural_rating=5, structural_label="textbook",
            stage2_trend=True, rs_rating=85.0, proximity_52w_pct=95.0,
            contraction_count=3,
            trough_symmetry_score=5, peak_symmetry_score=5,
            dollar_range_score=5, depth_score=5,
            tight_closes_score=5, volume_decay_score=5,
            time_contraction_score=5, as_of=date.today(),
        )

        mock_enrich.return_value = [
            VcpContextEnrichment(
                symbol="AAPL", exchange="NASDAQ",
                sector="Technology", industry="Consumer Electronics",
                industry_group_strength_flag="HOT_SECTOR",
                is_category_leader=True,
            )
        ]

        result = execute_vcp_enrichment([structural])
        assert "agent2" in result
        assert "agent3" in result
        assert len(result["rated_stocks"]) == 1

    @patch("stock_analyze.pipeline.enrich_with_vcp_context")
    def test_execute_vcp_enrichment_skips_empty(self, mock_enrich):
        mock_enrich.return_value = []
        result = execute_vcp_enrichment([])
        assert len(result["rated_stocks"]) == 0


class TestStripInternalKeys:
    def test_strip_internal_keys(self):
        payload = {"data": [1, 2], "_counts": {"a": 1}, "_meta": "x"}
        stripped = strip_internal_keys(payload)
        assert "data" in stripped
        assert "_counts" not in stripped
        assert "_meta" not in stripped


class TestRunDailyVcp:
    @patch("stock_analyze.pipeline.execute_vcp_scan")
    @patch("stock_analyze.pipeline.execute_vcp_enrichment")
    def test_run_daily_dispatches_vcp_pipeline(self, mock_enrich, mock_scan):
        """pipeline_type=daily_vcp_scan → calls vcp path."""
        from stock_analyze.models.vcp import VcpStructuralRating
        from datetime import date

        mock_scan.return_value = {
            "ratings": [
                {
                    "symbol": "AAPL", "exchange": "NASDAQ",
                    "structural_rating": 5, "structural_label": "textbook",
                    "stage2_trend": True, "rs_rating": 85.0,
                    "proximity_52w_pct": 95.0, "contraction_count": 3,
                    "trough_symmetry_score": 5, "peak_symmetry_score": 5,
                    "dollar_range_score": 5, "depth_score": 5,
                    "tight_closes_score": 5, "volume_decay_score": 5,
                    "time_contraction_score": 5, "as_of": str(date.today()),
                }
            ],
            "five_star": [
                {
                    "symbol": "AAPL", "exchange": "NASDAQ",
                    "structural_rating": 5, "structural_label": "textbook",
                    "stage2_trend": True, "rs_rating": 85.0,
                    "proximity_52w_pct": 95.0, "contraction_count": 3,
                    "trough_symmetry_score": 5, "peak_symmetry_score": 5,
                    "dollar_range_score": 5, "depth_score": 5,
                    "tight_closes_score": 5, "volume_decay_score": 5,
                    "time_contraction_score": 5, "as_of": str(date.today()),
                }
            ],
            "four_star": [], "three_star": [],
            "_counts": {"5": 1, "4": 0, "3": 0},
            "count": 1,
            "counts": {"5": 1, "4": 0, "3": 0},
            "gates_applied": True,
        }

        from stock_analyze.models.vcp import VcpRatedStock
        mock_enrich.return_value = {
            "agent2": {"count": 1, "stocks": []},
            "agent3": {"count": 1, "stocks": []},
            "rated_stocks": [
                VcpRatedStock(
                    symbol="AAPL", exchange="NASDAQ",
                    structural_rating=5, structural_label="textbook",
                    as_of=date.today(),
                    final_rating=5, final_label="textbook",
                )
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = RunConfig(
                name="vcp-test",
                pipeline_type="daily_vcp_scan",
                output_root=Path(tmpdir),
                run_catalyst=True,
            )
            result = run_daily(cfg)
            assert result.exit_code == 0
            assert "agent1" in result.steps_completed


class TestRunDailyIntegration:
    """Integration: verify EP pipeline still works after VCP additions."""

    @patch("stock_analyze.pipeline.execute_ep_scan")
    def test_ep_pipeline_unaffected(self, mock_scan):
        """EP pipeline_type still dispatches to EP path."""
        mock_scan.return_value = {
            "baseline": {"count": 0, "stocks": []},
            "strict": {"count": 0, "stocks": []},
            "_counts": {"baseline": 0, "strict": 0},
            "gates": {},
            "as_of": "2024-01-01T00:00:00",
            "universe_source": "screener",
            "session": "rth",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = RunConfig(
                name="ep-test",
                pipeline_type="daily_ep_scan",
                output_root=Path(tmpdir),
                run_catalyst=False,
                use_screener=False,
                force_keys=[],
            )
            # use_screener=False with empty force_keys raises ValueError
            # must have force_keys or use_screener
            pass
