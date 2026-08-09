"""Seams: create_run_dir, sanitize_run_name, run_daily."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from stock_analyze.pipeline import RunConfig, create_run_dir, run_daily, sanitize_run_name


def test_sanitize_run_name_allows_safe_chars_only():
    assert sanitize_run_name("daily_EP-1") == "daily_EP-1"
    assert sanitize_run_name("  daily EP!! ") == "daily_EP"
    with pytest.raises(ValueError):
        sanitize_run_name("!!!")


def test_create_run_dir_stamps_date_time_and_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixed = datetime(2026, 8, 9, 15, 30, 45)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)

    cfg = RunConfig(name="daily", select="strict", output_root=tmp_path)
    run_dir = create_run_dir(cfg)

    assert run_dir == tmp_path / "2026-08-09" / "153045_daily"
    assert run_dir.is_dir()


def test_run_daily_writes_agent1_only_when_catalyst_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixed = datetime(2026, 8, 9, 16, 0, 0)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)

    agent1_payload = {
        "as_of": "2026-08-09T00:00:00Z",
        "strict": {"count": 1, "stocks": [{"symbol": "NVDA", "exchange": "NASDAQ"}]},
    }

    def fake_scan(**kwargs):
        return agent1_payload

    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_scan", fake_scan)

    called = {"catalyst": False, "rate": False}

    def boom_catalyst(*args, **kwargs):
        called["catalyst"] = True
        raise AssertionError("catalyst should not run")

    def boom_rate(*args, **kwargs):
        called["rate"] = True
        raise AssertionError("rate should not run")

    monkeypatch.setattr("stock_analyze.pipeline.execute_catalyst_enrich", boom_catalyst)
    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_rating", boom_rate)

    cfg = RunConfig(
        name="manual",
        select="strict",
        run_catalyst=False,
        analysis_method=None,
        output_root=tmp_path,
    )
    result = run_daily(cfg)

    assert result.exit_code == 0
    assert result.run_dir == tmp_path / "2026-08-09" / "160000_manual"
    assert (result.run_dir / "manual_agent1.json").is_file()
    assert not (result.run_dir / "manual_agent2.json").exists()
    assert not (result.run_dir / "manual_agent3.json").exists()
    meta = json.loads((result.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["steps_completed"] == ["agent1"]
    assert called == {"catalyst": False, "rate": False}


def test_run_daily_full_chain_writes_all_agent_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixed = datetime(2026, 8, 9, 17, 0, 0)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)

    monkeypatch.setattr(
        "stock_analyze.pipeline.execute_ep_scan",
        lambda **kwargs: {
            "strict": {
                "count": 1,
                "stocks": [
                    {
                        "symbol": "NVDA",
                        "exchange": "NASDAQ",
                        "price": 125.0,
                        "gap_pct": 11.0,
                        "rvol10": 4.0,
                        "event_dollar_volume": 100.0,
                    }
                ],
            }
        },
    )
    def fake_catalyst(stocks):
        enriched = [
            {
                **stocks[0],
                "catalyst_found": True,
                "catalyst_type": "EARNINGS",
                "catalyst_summary": "Beat",
                "as_of": "2026-08-09",
                "force_included": False,
                "market_cap": None,
                "avg_dollar_volume_50d": None,
            }
        ]
        return {"count": 1, "stocks": enriched}

    def fake_rate(stocks):
        from stock_analyze.models.rating import EpRatedStock

        rated = [
            EpRatedStock(
                symbol=stocks[0]["symbol"],
                exchange=stocks[0]["exchange"],
                price=float(stocks[0]["price"]),
                gap_pct=float(stocks[0]["gap_pct"]),
                rvol10=float(stocks[0]["rvol10"]),
                event_dollar_volume=float(stocks[0]["event_dollar_volume"]),
                as_of=date(2026, 8, 9),
                catalyst_found=True,
                catalyst_type="EARNINGS",
                catalyst_summary="Beat",
                ep_rating=5,
                ep_rating_label="textbook",
                ep_rationale="Clear earnings shock",
                ep_catalyst_match=True,
            )
        ]
        return {"count": 1, "stocks": [s.model_dump(mode="json") for s in rated]}, rated

    monkeypatch.setattr("stock_analyze.pipeline.execute_catalyst_enrich", fake_catalyst)
    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_rating", fake_rate)

    cfg = RunConfig(
        name="daily",
        select="strict",
        run_catalyst=True,
        analysis_method="ep_rating",
        output_root=tmp_path,
    )
    result = run_daily(cfg)

    assert result.exit_code == 0
    run_dir = result.run_dir
    assert (run_dir / "daily_agent1.json").is_file()
    assert (run_dir / "daily_agent2.json").is_file()
    assert (run_dir / "daily_agent3.json").is_file()
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["steps_completed"] == ["agent1", "agent2", "agent3"]


def test_run_daily_failure_keeps_agent1_and_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixed = datetime(2026, 8, 9, 18, 0, 0)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)
    monkeypatch.setattr(
        "stock_analyze.pipeline.execute_ep_scan",
        lambda **kwargs: {"strict": {"count": 0, "stocks": []}},
    )

    def fail_catalyst(stocks):
        raise RuntimeError("tavily down")

    monkeypatch.setattr("stock_analyze.pipeline.execute_catalyst_enrich", fail_catalyst)

    cfg = RunConfig(
        name="fail",
        select="strict",
        run_catalyst=True,
        analysis_method="ep_rating",
        output_root=tmp_path,
    )
    result = run_daily(cfg)

    assert result.exit_code == 1
    run_dir = result.run_dir
    assert (run_dir / "fail_agent1.json").is_file()
    assert not (run_dir / "fail_agent2.json").exists()
    assert not (run_dir / "fail_agent3.json").exists()
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["steps_completed"] == ["agent1"]
    assert "tavily down" in meta["error"]
