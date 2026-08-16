"""Unit tests for job config mapping + artifact reading."""

from __future__ import annotations

import json

import pytest

from app.jobs import build_run_config, extract_counts, read_artifacts


def test_build_bo_config():
    cfg = build_run_config(
        {
            "pipeline_type": "daily_bo_scan",
            "force_symbols": "AAPL, MSFT",
            "bo_profile": "moderate-lose",
            "apply_gates": True,
            "name": "nightly",
        }
    )
    assert cfg.pipeline_type == "daily_bo_scan"
    assert cfg.name == "nightly"
    assert cfg.bo_profile == "moderate-lose"
    assert cfg.apply_gates is True
    assert [s for s, _ in cfg.force_keys] == ["AAPL", "MSFT"]


def test_build_ep_config():
    cfg = build_run_config(
        {"pipeline_type": "daily_ep_scan", "force_symbols": "AAPL", "select": "baseline"}
    )
    assert cfg.pipeline_type == "daily_ep_scan"
    assert cfg.select == "baseline"


def test_build_vcp_config():
    cfg = build_run_config(
        {"pipeline_type": "daily_vcp_scan", "force_symbols": "AAPL", "apply_gates": False}
    )
    assert cfg.pipeline_type == "daily_vcp_scan"
    assert cfg.apply_gates is False


def test_build_raises_on_empty_symbols():
    with pytest.raises(ValueError):
        build_run_config({"pipeline_type": "daily_bo_scan", "force_symbols": "   "})


def test_build_sweep_config():
    cfg = build_run_config(
        {
            "pipeline_type": "daily_bo_scan",
            "use_screener": True,
            "force_symbols": "",
            "apply_gates": True,
            "name": "market-sweep",
        }
    )
    assert cfg.pipeline_type == "daily_bo_scan"
    assert cfg.use_screener is True
    assert cfg.force_keys == []
    assert cfg.name == "market-sweep"


def test_read_artifacts_glob(tmp_path):
    (tmp_path / "run_meta.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    (tmp_path / "x_agent1.json").write_text(json.dumps({"ratings": []}), encoding="utf-8")
    (tmp_path / "x_agent3.json").write_text(json.dumps({"count": 0}), encoding="utf-8")

    artifacts = read_artifacts(tmp_path)
    assert artifacts["meta"]["name"] == "x"
    assert "agent1" in artifacts
    assert "agent3" in artifacts
    assert "agent2" not in artifacts  # catalyst-off path


def test_extract_counts_ep():
    artifacts = {"agent1": {"baseline": {"count": 3}, "strict": {"count": 1}}}
    assert extract_counts(artifacts, "daily_ep_scan") == {"baseline": 3, "strict": 1}


def test_extract_counts_vcp_bo():
    artifacts = {"agent1": {"counts": {"5": 1, "4": 2, "3": 5}}}
    assert extract_counts(artifacts, "daily_bo_scan") == {"5": 1, "4": 2, "3": 5}
