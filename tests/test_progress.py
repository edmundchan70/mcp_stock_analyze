"""Seams: RunProgress stage lines + ticker lifecycle (non-TTY console)."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from stock_analyze.progress import RunProgress


def _progress() -> tuple[RunProgress, StringIO]:
    buf = StringIO()
    rp = RunProgress(console=Console(file=buf, force_terminal=False))
    return rp, buf


def test_stage_and_stage_done_write_lines():
    rp, buf = _progress()
    rp.stage("Agent 1 — fetching universe")
    rp.stage_done("Agent 1 done (baseline=42, strict=17)")
    out = buf.getvalue()
    assert "Agent 1 — fetching universe" in out
    assert "Agent 1 done (baseline=42, strict=17)" in out


def test_ticker_lifecycle_does_not_raise_and_tracks_updates():
    rp, _ = _progress()
    rp.begin_ticker(2, "Catalyst")
    rp.ticker(1, 2, "NVDA", "searching news")
    rp.ticker(2, 2, "AMD", "compressing")
    rp.end_ticker()
    assert rp._task_id is None
    assert rp.progress.tasks == []
