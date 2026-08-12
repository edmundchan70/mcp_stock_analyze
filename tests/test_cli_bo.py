"""Unit tests for BO CLI subcommands (argparse)."""

import pytest
from stock_analyze.cli import build_parser


class TestBoSubcommands:
    def test_bo_subcommand_exists(self):
        parser = build_parser()
        help_text = parser.format_help()
        assert "bo" in help_text

    def test_bo_scan_subcommand_exists(self):
        parser = build_parser()
        help_text = parser.format_help()
        assert "bo-scan" in help_text

    def test_bo_enrich_subcommand_exists(self):
        parser = build_parser()
        help_text = parser.format_help()
        assert "bo-enrich" in help_text

    def test_bo_enrich_accepts_input_arg(self):
        parser = build_parser()
        args = parser.parse_args(["bo-enrich", "--in", "test.json"])
        assert args.command == "bo-enrich"
        assert args.in_path == "test.json"

    def test_bo_accepts_limit(self):
        parser = build_parser()
        args = parser.parse_args(["bo", "--limit", "100"])
        assert args.limit == 100

    def test_bo_accepts_no_gates(self):
        parser = build_parser()
        args = parser.parse_args(["bo", "--no-gates"])
        assert args.no_gates is True

    def test_bo_scan_accepts_out(self):
        parser = build_parser()
        args = parser.parse_args(["bo-scan", "--out", "output.json"])
        assert args.out == "output.json"

    def test_bo_enrich_accepts_min_rating(self):
        parser = build_parser()
        args = parser.parse_args(
            ["bo-enrich", "--in", "test.json", "--min-rating", "3"]
        )
        assert args.min_rating == 3

    def test_bo_accepts_force(self):
        parser = build_parser()
        args = parser.parse_args(["bo", "--force", "AAPL,MSFT,TSLA"])
        assert args.force == "AAPL,MSFT,TSLA"

    def test_bo_scan_accepts_force(self):
        parser = build_parser()
        args = parser.parse_args(["bo-scan", "--force", "AAPL,MSFT"])
        assert args.force == "AAPL,MSFT"

    def test_bo_enrich_default_min_rating(self):
        parser = build_parser()
        args = parser.parse_args(["bo-enrich", "--in", "test.json"])
        assert args.min_rating == 4

    def test_vcp_and_ep_still_work(self):
        """Existing VCP/EP commands should still be available."""
        parser = build_parser()
        help_text = parser.format_help()
        assert "vcp" in help_text
        assert "vcp-scan" in help_text
        assert "ep" in help_text
        assert "catalyst" in help_text
        assert "rate" in help_text

    def test_default_command_none_when_no_args(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None
