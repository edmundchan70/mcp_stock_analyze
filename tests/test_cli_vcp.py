"""Unit tests for VCP CLI subcommands (argparse)."""

import pytest
from stock_analyze.cli import build_parser


class TestVcpSubcommands:
    def test_vcp_subcommand_exists(self):
        parser = build_parser()
        # --help should show vcp options
        help_text = parser.format_help()
        assert "vcp" in help_text

    def test_vcp_scan_subcommand_exists(self):
        parser = build_parser()
        help_text = parser.format_help()
        assert "vcp-scan" in help_text

    def test_vcp_enrich_subcommand_exists(self):
        parser = build_parser()
        help_text = parser.format_help()
        assert "vcp-enrich" in help_text

    def test_vcp_enrich_accepts_input_arg(self):
        parser = build_parser()
        args = parser.parse_args(["vcp-enrich", "--in", "test.json"])
        assert args.command == "vcp-enrich"
        assert args.in_path == "test.json"

    def test_vcp_accepts_limit(self):
        parser = build_parser()
        args = parser.parse_args(["vcp", "--limit", "100"])
        assert args.limit == 100

    def test_vcp_accepts_no_gates(self):
        parser = build_parser()
        args = parser.parse_args(["vcp", "--no-gates"])
        assert args.no_gates is True

    def test_vcp_scan_accepts_out(self):
        parser = build_parser()
        args = parser.parse_args(["vcp-scan", "--out", "output.json"])
        assert args.out == "output.json"

    def test_vcp_enrich_accepts_min_rating(self):
        parser = build_parser()
        args = parser.parse_args(
            ["vcp-enrich", "--in", "test.json", "--min-rating", "3"]
        )
        assert args.min_rating == 3

    def test_vcp_accepts_force(self):
        parser = build_parser()
        args = parser.parse_args(["vcp", "--force", "AAPL,MSFT,TSLA"])
        assert args.force == "AAPL,MSFT,TSLA"

    def test_vcp_scan_accepts_force(self):
        parser = build_parser()
        args = parser.parse_args(["vcp-scan", "--force", "AAPL,MSFT"])
        assert args.force == "AAPL,MSFT"

    def test_default_command_none_when_no_args(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_ep_command_still_works(self):
        """EP commands should still be available after VCP additions."""
        parser = build_parser()
        help_text = parser.format_help()
        assert "ep" in help_text
        assert "catalyst" in help_text
        assert "rate" in help_text

    def test_vcp_enrich_default_min_rating(self):
        parser = build_parser()
        args = parser.parse_args(["vcp-enrich", "--in", "test.json"])
        assert args.min_rating == 4
