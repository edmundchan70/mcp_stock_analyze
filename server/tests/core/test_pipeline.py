"""Seams: create_run_dir, sanitize_run_name, execute_ep_scan, run_daily."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from stock_analyze.pipeline import (
    RunConfig,
    create_run_dir,
    execute_ep_scan,
    run_daily,
    sanitize_run_name,
)


def test_sanitize_run_name_allows_safe_chars_only():
    assert sanitize_run_name("daily_EP-1") == "daily_EP-1"
    assert sanitize_run_name("  daily EP!! ") == "daily_EP"
    with pytest.raises(ValueError):
        sanitize_run_name("!!!")


def test_create_run_dir_stamps_date_time_and_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixed = datetime(2026, 8, 9, 15, 30, 45)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)

    cfg = RunConfig(name="daily", select="strict", output_root=tmp_path, force_keys=[("AAPL", "NASDAQ")])
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
        force_keys=[("AAPL", "NASDAQ")],
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
    def fake_catalyst(stocks, on_ticker=None):
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

    def fake_rate(stocks, on_ticker=None):
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
        force_keys=[("AAPL", "NASDAQ")],
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


def test_run_daily_passes_force_keys_to_execute_ep_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixed = datetime(2026, 8, 9, 19, 0, 0)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)

    seen: dict = {}

    def fake_scan(**kwargs):
        seen.update(kwargs)
        return {"strict": {"count": 0, "stocks": []}}

    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_scan", fake_scan)

    keys = [("AAPL", "NASDAQ")]
    cfg = RunConfig(
        name="force",
        select="strict",
        run_catalyst=False,
        analysis_method=None,
        force_keys=[("AAPL", "NASDAQ")],
        output_root=tmp_path,
    )
    result = run_daily(cfg)

    assert result.exit_code == 0
    assert seen.get("force_keys") == keys
    meta = json.loads((result.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["force_include_count"] == 1


def test_execute_ep_scan_paste_only_skips_screener(monkeypatch: pytest.MonkeyPatch):
    """Paste-only: force_keys → Polygon resolved, no screener call."""
    monkeypatch.setattr(
        "stock_analyze.pipeline.resolve_force_symbol",
        lambda sym: {
            "name": f"NYSE:{sym}",
            "symbol": sym,
            "exchange": "NYSE",
            "market_cap": 800_000_000,
            "description": f"{sym} Inc.",
        },
    )
    fake_ohlcv = {
        "name": "NYSE:JHX", "symbol": "JHX", "exchange": "NYSE",
        "close": 25.0, "open": 25.0, "prior_close": 22.73,
        "volume": 1000000, "relative_volume_10d_calc": 4.0,
        "Value.Traded": 30000000, "avg_dollar_volume_50d": 5000000,
    }
    monkeypatch.setattr("stock_analyze.pipeline.to_ep_row", lambda sym: fake_ohlcv)

    payload = execute_ep_scan(
        force_keys=[("JHX", "NYSE")],
        select="strict",
        limit=300,
        use_screener=False,
        apply_gates=True,
    )

    assert payload["universe_source"] == "force"
    assert payload["strict"]["count"] == 1
    assert payload["strict"]["stocks"][0]["symbol"] == "JHX"


def test_execute_ep_scan_use_screener_false_requires_force_keys():
    with pytest.raises(ValueError, match="force_keys"):
        execute_ep_scan(
            force_keys=None,
            select="strict",
            limit=300,
            use_screener=False,
        )


def test_execute_ep_scan_apply_gates_false_keeps_weak_names(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "stock_analyze.pipeline.resolve_force_symbol",
        lambda sym: {
            "name": f"NASDAQ:{sym}",
            "symbol": sym,
            "exchange": "NASDAQ",
            "market_cap": 50_000_000,
            "description": f"{sym} Inc.",
        },
    )
    fake_ohlcv = {
        "name": "NASDAQ:WEAK", "symbol": "WEAK", "exchange": "NASDAQ",
        "close": 5.0, "open": 4.8, "prior_close": 4.57,
        "gap": 5.0, "volume": 1000000, "relative_volume_10d_calc": 2.0,
        "Value.Traded": 1000000, "avg_dollar_volume_50d": 500000,
    }
    monkeypatch.setattr("stock_analyze.pipeline.to_ep_row", lambda sym: fake_ohlcv)

    payload = execute_ep_scan(
        force_keys=[("WEAK", "NASDAQ")],
        select="both",
        limit=300,
        use_screener=False,
        apply_gates=False,
    )

    assert payload["strict"]["count"] == 1
    assert payload["strict"]["stocks"][0]["symbol"] == "WEAK"
    assert payload["baseline"]["count"] == 1


def test_execute_ep_scan_empty_force_keys_raises():
    """No force_keys → ValueError (paste-only)."""
    with pytest.raises(ValueError, match="force_keys"):
        execute_ep_scan(select="strict", limit=300)


def test_run_daily_records_use_screener_and_apply_gates_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixed = datetime(2026, 8, 9, 20, 0, 0)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)

    seen: dict = {}

    def fake_scan(**kwargs):
        seen.update(kwargs)
        return {"strict": {"count": 0, "stocks": []}, "universe_source": "force"}

    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_scan", fake_scan)

    cfg = RunConfig(
        name="paste",
        select="strict",
        run_catalyst=False,
        analysis_method=None,
        force_keys=[("AAPL", "NASDAQ")],
        use_screener=False,
        apply_gates=False,
        output_root=tmp_path,
    )
    result = run_daily(cfg)

    assert result.exit_code == 0
    assert seen.get("use_screener") is False
    assert seen.get("apply_gates") is False
    meta = json.loads((result.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["use_screener"] is False
    assert meta["apply_gates"] is False
    assert meta["force_include_count"] == 1


def test_run_daily_failure_keeps_agent1_and_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixed = datetime(2026, 8, 9, 18, 0, 0)
    monkeypatch.setattr("stock_analyze.pipeline._now", lambda: fixed)
    monkeypatch.setattr(
        "stock_analyze.pipeline.execute_ep_scan",
        lambda **kwargs: {"strict": {"count": 0, "stocks": []}},
    )

    def fail_catalyst(stocks, on_ticker=None):
        raise RuntimeError("tavily down")

    monkeypatch.setattr("stock_analyze.pipeline.execute_catalyst_enrich", fail_catalyst)

    cfg = RunConfig(
        name="fail",
        select="strict",
        run_catalyst=True,
        analysis_method="ep_rating",
        output_root=tmp_path,
        force_keys=[("AAPL", "NASDAQ")],
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


# ── resilience tests ────────────────────────────────────────────────────


def test_execute_ep_scan_survives_force_fetch_timeout(monkeypatch):
    """resolve_force_symbol succeeds, to_ep_row returns a valid row → run
    completes with the stock present."""

    monkeypatch.setattr(
        "stock_analyze.pipeline.resolve_force_symbol",
        lambda sym: {
            "name": f"NYSE:{sym}",
            "symbol": sym,
            "exchange": "NYSE",
            "market_cap": 500000000,
            "description": f"{sym} Inc.",
        },
    )
    fake_ohlcv = {
        "name": "NYSE:JHX", "symbol": "JHX", "exchange": "NYSE",
        "close": 25.0, "open": 25.0, "prior_close": 22.73,
        "volume": 1000000, "relative_volume_10d_calc": 4.0,
        "Value.Traded": 25000000, "avg_dollar_volume_50d": 5000000,
    }
    monkeypatch.setattr("stock_analyze.pipeline.to_ep_row", lambda sym: fake_ohlcv)

    payload = execute_ep_scan(
        force_keys=[("JHX", "NYSE")],
        select="strict",
        limit=300,
        use_screener=False,
        apply_gates=True,
    )

    assert payload["strict"]["count"] == 1
    assert payload["strict"]["stocks"][0]["symbol"] == "JHX"


def test_execute_ep_scan_drops_missing_symbols_without_crash(monkeypatch):
    """resolve_force_symbol returns None → _failed_force recorded, counts 0."""

    monkeypatch.setattr("stock_analyze.pipeline.resolve_force_symbol", lambda _sym: None)

    payload = execute_ep_scan(
        force_keys=[("MISSING", "NASDAQ")],
        select="strict",
        limit=300,
        use_screener=False,
        apply_gates=True,
    )

    assert payload["strict"]["count"] == 0
    assert len(payload.get("_failed_force") or []) == 1
    assert payload["_failed_force"][0]["symbol"] == "MISSING"


def test_execute_ep_scan_survives_symbol_resolution_failure(monkeypatch):
    """resolve_force_symbol fails for one, succeeds for another → partial result."""

    def _resolve(sym):
        if sym == "BADSYM":
            return None
        return {
            "name": f"NASDAQ:{sym}",
            "symbol": sym,
            "exchange": "NASDAQ",
            "market_cap": 5_000_000_000,
            "description": f"{sym} Inc.",
        }

    monkeypatch.setattr("stock_analyze.pipeline.resolve_force_symbol", _resolve)

    fake_ohlcv = {
        "name": "POLYGON:JHX", "symbol": "JHX", "exchange": "NASDAQ",
        "close": 25.0, "open": 25.0, "prior_close": 22.73,
        "volume": 1000000, "relative_volume_10d_calc": 4.0,
        "Value.Traded": 30000000, "avg_dollar_volume_50d": 5000000,
    }
    monkeypatch.setattr("stock_analyze.pipeline.to_ep_row", lambda sym: fake_ohlcv)

    payload = execute_ep_scan(
        force_keys=[("BADSYM", "NASDAQ"), ("JHX", "NASDAQ")],
        select="strict",
        limit=300,
        use_screener=False,
        apply_gates=True,
    )

    assert payload["universe_source"] == "force"
    assert len(payload.get("_failed_force") or []) == 1


def test_force_symbol_resolves_correctly(monkeypatch):
    """resolve_force_symbol returns NYSE row → JHX stays in universe."""

    def _resolve(sym):
        return {
            "name": f"NYSE:{sym}",
            "symbol": sym,
            "exchange": "NYSE",
            "market_cap": 800000000,
            "description": f"{sym} Inc.",
        }

    monkeypatch.setattr("stock_analyze.pipeline.resolve_force_symbol", _resolve)

    fake_ohlcv = {
        "name": "NYSE:JHX", "symbol": "JHX", "exchange": "NYSE",
        "close": 25.0, "open": 25.0, "prior_close": 22.73,
        "volume": 1000000, "relative_volume_10d_calc": 4.0,
        "Value.Traded": 30000000, "avg_dollar_volume_50d": 5000000,
    }
    monkeypatch.setattr("stock_analyze.pipeline.to_ep_row", lambda sym: fake_ohlcv)

    payload = execute_ep_scan(
        force_keys=[("JHX", "NASDAQ")],
        select="strict",
        limit=300,
        use_screener=False,
        apply_gates=True,
    )

    symbols = {s["symbol"] for s in payload["strict"]["stocks"]}
    assert "JHX" in symbols
