"""Unit tests for job config mapping + artifact reading."""

from __future__ import annotations

import asyncio
import json
import types
from typing import Any

import pytest

from app.jobs import build_run_config, extract_counts, read_artifacts, run_graph_job
from app.reporter import EventReporter
from stock_analyze.tools.protocol import PortDef, ToolSpec
from stock_analyze.tools.registry import REGISTRY
from stock_analyze.tools.walker import run_graph

from fakes import FakeRepo


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


def test_ep_scanner_vars_include_technical_group():
    """The EP family exposes the technical test toggles + thresholds."""
    from stock_analyze.tools.variables import SCANNER_GROUPS, scanner_visible_vars

    assert "EP technical" in SCANNER_GROUPS["ep"]
    keys = {v.key for v in scanner_visible_vars("ep")}
    assert {
        "ep_features_enabled",
        "ep_keep_if_any",
        "ep_feature_base_detected",
        "ep_feature_volume_spike",
        "ep_feature_pullback_contrast",
        "ep_feature_ema_support",
        "ep_feature_vwap_support",
        "ep_spike_min",
        "ep_pullback_vol_ratio",
        "ep_pullback_depth_pct",
        "ep_ema_touch_pct",
        "ep_vwap_touch_pct",
        "ep_base_min_days",
        "ep_base_max_days",
    }.issubset(keys)
    by_key = {v.key: v for v in scanner_visible_vars("ep")}
    assert by_key["ep_features_enabled"].default is True
    assert by_key["ep_spike_min"].default == 3.0


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


# ── live progress wiring (graph runs) ──────────────────────────────


class _FakeProgress:
    """Minimal RunProgress duck-type recording begin/ticker/end calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, ...]] = []

    def begin_ticker(self, total: int, description: str, throttle: int = 0) -> None:
        self.calls.append(("begin", total, description, throttle))

    def ticker(self, index: int, total: int, symbol: str, action: str) -> None:
        self.calls.append(("ticker", index, total, symbol, action))

    def end_ticker(self) -> None:
        self.calls.append(("end",))


def _stub_spec(tool_id: str, callable, in_port: str, in_type: str, out_port: str, out_type: str) -> ToolSpec:
    return ToolSpec(
        id=tool_id,
        name=tool_id,
        description=tool_id,
        phase=1,
        inputs=[PortDef(id=in_port, type=in_type, required=True, label=in_port)],
        outputs=[PortDef(id=out_port, type=out_type, required=True, label=out_port)],
        callable=callable,
    )


def _restore(id_: str, old: ToolSpec | None) -> None:
    if old is not None:
        REGISTRY[id_] = old
    else:
        REGISTRY.pop(id_, None)


def test_run_graph_injects_progress_into_node_params():
    seen: dict[str, Any] = {}

    def scanner_callable(inputs, params):
        seen["scanner_progress"] = params.get("__progress__")
        seen["scanner_inputs"] = len(inputs.get("universe", []))
        return [{"symbol": "AAPL", "exchange": "NASDAQ"}]

    def search_callable(inputs, params):
        seen["search_progress"] = params.get("__progress__")
        return []

    old_scanner = REGISTRY.get("scanner")
    old_search = REGISTRY.get("search")
    REGISTRY["scanner"] = _stub_spec("scanner", scanner_callable, "universe", "symbolkey", "bucket", "scan_rows")
    REGISTRY["search"] = _stub_spec("search", search_callable, "in", "enriched_rows", "out", "enriched_rows")
    try:
        progress = _FakeProgress()
        definition = {
            "version": 1,
            "name": "t",
            "universe": {"source": "paste", "force_keys": [["AAPL", "NASDAQ"]]},
            "nodes": [
                {"id": "sc_1", "tool_id": "scanner", "params": {}},
                {"id": "sr_1", "tool_id": "search", "params": {}},
            ],
            "edges": [
                {"id": "e1", "source": "universe", "source_port": "out", "target": "sc_1", "target_port": "universe"},
                {"id": "e2", "source": "sc_1", "source_port": "bucket", "target": "sr_1", "target_port": "in"},
            ],
        }
        result = run_graph(
            definition,
            [{"symbol": "AAPL", "exchange": "NASDAQ"}],
            progress=progress,
        )
        assert result.nodes["sc_1"].status == "ok"
        assert result.nodes["sr_1"].status == "ok"
        assert seen["scanner_progress"] is progress
        assert seen["search_progress"] is progress
    finally:
        _restore("scanner", old_scanner)
        _restore("search", old_search)


def test_scanner_callable_forwards_batch_progress(monkeypatch):
    from stock_analyze.tools.builtins import _scanner_callable

    def fake_execute_bo_scan(*, force_keys=None, limit=300, apply_gates=True, batch_progress=None):
        assert batch_progress is not None
        batch_progress.begin_ticker(2, "Batch OHLCV", throttle=5)
        batch_progress.ticker(1, 2, "AAPL", "fetch")
        batch_progress.end_ticker()
        return {"ratings": [{"symbol": "AAPL", "exchange": "NASDAQ", "rating": 4}]}

    monkeypatch.setattr("stock_analyze.pipeline.execute_bo_scan", fake_execute_bo_scan)
    progress = _FakeProgress()
    out = _scanner_callable(
        {"universe": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
        {"family": "bo", "__progress__": progress},
    )
    assert out == [{"symbol": "AAPL", "exchange": "NASDAQ", "rating": 4}]
    assert [c[0] for c in progress.calls] == ["begin", "ticker", "end"]
    assert progress.calls[0][1:] == (2, "Batch OHLCV", 5)


def test_scanner_callable_forwards_ep_feature_params(monkeypatch):
    from stock_analyze.tools.builtins import _scanner_callable

    captured: dict[str, Any] = {}

    def fake_execute_ep_scan(
        *,
        force_keys=None,
        select="strict",
        limit=300,
        apply_gates=True,
        batch_progress=None,
        ep_features=False,
        ep_feature_keys=None,
        ep_keep_if_any=True,
        ep_thresholds=None,
    ):
        captured.update(
            force_keys=force_keys,
            select=select,
            limit=limit,
            apply_gates=apply_gates,
            ep_features=ep_features,
            ep_feature_keys=ep_feature_keys,
            ep_keep_if_any=ep_keep_if_any,
            ep_thresholds=ep_thresholds,
        )
        stock = {"symbol": "AAPL", "exchange": "NASDAQ", "volume_spike": True, "ep_keep": True}
        return {
            "baseline": {"count": 1, "stocks": [stock]},
            "strict": {"count": 1, "stocks": [stock]},
        }

    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_scan", fake_execute_ep_scan)
    out = _scanner_callable(
        {"universe": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
        {
            "family": "ep",
            "ep_features_enabled": True,
            "ep_keep_if_any": True,
            "ep_feature_base_detected": False,
            "ep_spike_min": 2.5,
        },
    )
    assert captured["ep_features"] is True
    assert captured["ep_keep_if_any"] is True
    assert "base_detected" not in captured["ep_feature_keys"]
    assert "volume_spike" in captured["ep_feature_keys"]
    assert captured["ep_thresholds"].spike_min == 2.5
    # both buckets mirror the same survivor list → row is deduped
    assert len(out) == 1
    assert out[0]["volume_spike"] is True


def test_scanner_callable_ep_feature_defaults(monkeypatch):
    from stock_analyze.tools.builtins import _scanner_callable

    captured: dict[str, Any] = {}

    def fake_execute_ep_scan(
        *,
        force_keys=None,
        select="strict",
        limit=300,
        apply_gates=True,
        batch_progress=None,
        ep_features=False,
        ep_feature_keys=None,
        ep_keep_if_any=True,
        ep_thresholds=None,
    ):
        captured.update(
            ep_features=ep_features,
            ep_feature_keys=ep_feature_keys,
            ep_keep_if_any=ep_keep_if_any,
            ep_thresholds=ep_thresholds,
        )
        return {"baseline": {"count": 0, "stocks": []}, "strict": {"count": 0, "stocks": []}}

    monkeypatch.setattr("stock_analyze.pipeline.execute_ep_scan", fake_execute_ep_scan)
    _scanner_callable(
        {"universe": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
        {"family": "ep"},
    )
    # defaults: technical test ON, keep-if-any ON, all 5 features enabled, defaults thresholds
    assert captured["ep_features"] is True
    assert captured["ep_keep_if_any"] is True
    assert captured["ep_feature_keys"] == [
        "base_detected",
        "volume_spike",
        "pullback_contrast",
        "ema_support",
        "vwap_support",
    ]
    assert captured["ep_thresholds"] is None


def test_search_callable_forwards_on_ticker_ep(monkeypatch):
    from stock_analyze.tools.builtins import _search_callable

    def fake_enrich(rows, checkpoint=None, on_ticker=None):
        assert on_ticker is not None
        on_ticker(1, 1, "AAPL", "searching news")
        return [{"symbol": "AAPL", "exchange": "NASDAQ", "catalyst_summary": "x"}]

    def fake_rate(rows, checkpoint=None, on_ticker=None):
        assert on_ticker is not None
        on_ticker(1, 1, "AAPL", "rating")
        return [
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "ep_rating": 4,
                "catalyst_type": "EARNINGS",
                "ep_rationale": "r",
            }
        ]

    monkeypatch.setattr("stock_analyze.agents.catalyst.enrich_with_catalysts", fake_enrich)
    monkeypatch.setattr("stock_analyze.agents.rating.rate_ep_catalysts", fake_rate)

    progress = _FakeProgress()
    out = _search_callable(
        {"in": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
        {"__progress__": progress},
    )
    assert out[0]["ep_rating"] == 4
    begins = [c for c in progress.calls if c[0] == "begin"]
    assert len(begins) == 2  # catalyst search + EP rating spans
    assert len([c for c in progress.calls if c[0] == "ticker"]) == 2


def test_search_callable_forwards_on_ticker_vcp(monkeypatch):
    from stock_analyze.tools.builtins import _search_callable

    def fake_vcp_enrich(rows, checkpoint=None, on_ticker=None):
        assert on_ticker is not None
        on_ticker(1, 1, "TSLA", "searching sector")
        return [{"symbol": "TSLA", "exchange": "NASDAQ", "is_category_leader": True}]

    monkeypatch.setattr("stock_analyze.agents.enrichment.enrich_with_vcp_context", fake_vcp_enrich)

    progress = _FakeProgress()
    out = _search_callable(
        {"in": [{"symbol": "TSLA", "exchange": "NASDAQ", "structural_rating": 4}]},
        {"__progress__": progress},
    )
    assert out[0]["enrichment"]["is_category_leader"] is True
    assert [c[0] for c in progress.calls] == ["begin", "ticker", "end"]


async def test_run_graph_job_wires_event_reporter(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_resolve(params):
        return [{"symbol": "AAPL", "exchange": "NASDAQ"}], {
            "source": "paste",
            "force_keys": [["AAPL", "NASDAQ"]],
            "scan_id": None,
        }

    def fake_validate(definition, tools=None):
        return []

    def fake_run_graph(definition, universe_rows, **kwargs):
        captured["progress"] = kwargs.get("progress")
        return types.SimpleNamespace(
            cancelled=False,
            degraded=False,
            nodes={},
            merge_table={"count": 0, "columns": [], "rows": []},
        )

    monkeypatch.setattr("app.jobs.resolve_universe", fake_resolve)
    monkeypatch.setattr("app.jobs.validate_graph", fake_validate)
    monkeypatch.setattr("app.jobs.run_graph", fake_run_graph)

    repo = FakeRepo()
    await repo.create_run("r1", "g", "daily_bo_scan", {})
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    await run_graph_job(
        "r1",
        {
            "graph": {"name": "g", "nodes": [], "edges": []},
            "universe_source": "paste",
            "force_symbols": "AAPL",
        },
        repo,
        loop,
        queue,
    )
    assert isinstance(captured["progress"], EventReporter)
    assert repo.runs["r1"]["status"] == "succeeded"
    terminal = await queue.get()
    assert terminal["type"] == "done"


# ── zhao daily scan_signals streak hooks ──────────────────────────


def test_zhao_daily_scanner_nodes_detects_only_daily():
    from app.jobs import _zhao_daily_scanner_nodes

    graph = {
        "nodes": [
            {"id": "sc_1", "tool_id": "scanner", "params": {"family": "zhao", "zhao_variant": "daily"}},
            {"id": "sc_2", "tool_id": "scanner", "params": {"family": "zhao", "zhao_variant": "realtime"}},
            {"id": "sc_3", "tool_id": "scanner", "params": {"family": "ep"}},
            {"id": "r_1", "tool_id": "report", "params": {}},
        ]
    }
    assert _zhao_daily_scanner_nodes(graph) == ["sc_1"]


async def test_streak_overrides_injects_streaks(monkeypatch):
    from app.jobs import _streak_overrides

    repo = FakeRepo()
    await repo.record_scan_signals(["AAPL", "MSFT"], "zhao", "daily", signal_date="2026-08-19")
    await repo.record_scan_signals(["AAPL"], "zhao", "daily", signal_date="2026-08-18")

    graph = {
        "nodes": [
            {"id": "sc_1", "tool_id": "scanner", "params": {"family": "zhao", "zhao_variant": "daily"}},
            {"id": "sc_2", "tool_id": "scanner", "params": {"family": "zhao", "zhao_variant": "realtime"}},
        ]
    }
    overrides = await _streak_overrides(
        graph,
        [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "TSLA"}],
        repo,
    )
    assert set(overrides) == {"sc_1"}
    assert overrides["sc_1"]["__streaks__"]["AAPL"] == 2
    assert overrides["sc_1"]["__streaks__"]["MSFT"] == 1
    assert "TSLA" not in overrides["sc_1"]["__streaks__"]


async def test_record_zhao_signals_writes_survivors():
    from app.jobs import _record_zhao_signals

    repo = FakeRepo()
    result = types.SimpleNamespace(
        nodes={
            "sc_1": types.SimpleNamespace(
                output_rows={"bucket": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]}
            ),
            "sc_2": types.SimpleNamespace(
                output_rows={"bucket": [{"symbol": "TSLA"}]}
            ),
        }
    )
    graph = {
        "nodes": [
            {"id": "sc_1", "tool_id": "scanner", "params": {"family": "zhao", "zhao_variant": "daily"}},
            {"id": "sc_2", "tool_id": "scanner", "params": {"family": "zhao", "zhao_variant": "realtime"}},
        ]
    }
    await _record_zhao_signals(result, graph, repo)
    symbols = {s["symbol"] for s in repo.signals}
    assert symbols == {"AAPL", "MSFT"}  # realtime node not recorded


def test_scanner_callable_forwards_zhao_params(monkeypatch):
    from stock_analyze.tools.builtins import _scanner_callable

    captured: dict[str, Any] = {}

    def fake_execute_zhao_scan(
        *,
        force_keys=None,
        variant="realtime",
        benchmark="SPY",
        apply_gates=True,
        sma20_buffer_pct=0.0,
        min_margin_pct=1.0,
        min_rs_pct=0.0,
        max_high_dist_pct=15.0,
        streaks=None,
        batch_progress=None,
    ):
        captured.update(
            force_keys=force_keys,
            variant=variant,
            benchmark=benchmark,
            sma20_buffer_pct=sma20_buffer_pct,
            min_margin_pct=min_margin_pct,
            min_rs_pct=min_rs_pct,
            max_high_dist_pct=max_high_dist_pct,
            streaks=streaks,
        )
        return {
            "ratings": [{"symbol": "AAPL", "exchange": "NASDAQ", "strength": 5}],
            "count": 1,
        }

    monkeypatch.setattr("stock_analyze.pipeline.execute_zhao_scan", fake_execute_zhao_scan)
    out = _scanner_callable(
        {"universe": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
        {
            "family": "zhao",
            "zhao_variant": "daily",
            "zhao_benchmark": "QQQ",
            "zhao_sma20_buffer_pct": 0.5,
            "zhao_min_margin_pct": 2.0,
            "zhao_min_rs_pct": 3.0,
            "zhao_max_high_dist_pct": 20.0,
            "__streaks__": {"AAPL": 2},
        },
    )
    assert out == [{"symbol": "AAPL", "exchange": "NASDAQ", "strength": 5}]
    assert captured["variant"] == "daily"
    assert captured["benchmark"] == "QQQ"
    assert captured["sma20_buffer_pct"] == 0.5
    assert captured["streaks"] == {"AAPL": 2}


def test_scanner_callable_forwards_premarket_params(monkeypatch):
    from stock_analyze.tools.builtins import _scanner_callable

    captured: dict[str, Any] = {}

    def fake_execute_premarket_scan(
        *,
        force_keys=None,
        min_change_pct=5.0,
        min_vol_mult=0.0,
        cap=300,
        apply_gates=True,
        batch_progress=None,
    ):
        captured.update(
            force_keys=force_keys,
            min_change_pct=min_change_pct,
            min_vol_mult=min_vol_mult,
            cap=cap,
        )
        return {
            "ratings": [{"symbol": "AAPL", "exchange": "NASDAQ", "strength": 4}],
            "count": 1,
        }

    monkeypatch.setattr("stock_analyze.pipeline.execute_premarket_scan", fake_execute_premarket_scan)
    out = _scanner_callable(
        {"universe": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
        {
            "family": "premarket",
            "premarket_min_change_pct": 7.0,
            "premarket_min_vol_mult": 2.0,
            "premarket_cap": 100,
        },
    )
    assert out == [{"symbol": "AAPL", "exchange": "NASDAQ", "strength": 4}]
    assert captured["min_change_pct"] == 7.0
    assert captured["min_vol_mult"] == 2.0
    assert captured["cap"] == 100

