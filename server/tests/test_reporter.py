"""Unit tests for EventReporter — the RunProgress duck-type adapter."""

from __future__ import annotations

import asyncio

import pytest

from app.reporter import EventReporter


async def _drain(queue: asyncio.Queue) -> list[dict]:
    await asyncio.sleep(0)  # run call_soon_threadsafe callbacks
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_stage_emits_event():
    queue: asyncio.Queue = asyncio.Queue()
    reporter = EventReporter(queue, asyncio.get_running_loop())
    reporter.stage("hello")
    assert await _drain(queue) == [{"type": "stage", "text": "hello"}]


@pytest.mark.asyncio
async def test_stage_done_and_fail():
    queue: asyncio.Queue = asyncio.Queue()
    reporter = EventReporter(queue, asyncio.get_running_loop())
    reporter.stage_done("done")
    reporter.fail("boom")
    assert await _drain(queue) == [
        {"type": "stage_done", "text": "done"},
        {"type": "fail", "text": "boom"},
    ]


@pytest.mark.asyncio
async def test_ticker_throttle():
    queue: asyncio.Queue = asyncio.Queue()
    reporter = EventReporter(queue, asyncio.get_running_loop())
    reporter.begin_ticker(10, "Resolving", throttle=2)
    reporter.ticker(1, 10, "AAPL", "x")  # skipped (1 % 2 != 0)
    reporter.ticker(2, 10, "AAPL", "x")  # emitted
    reporter.ticker(3, 10, "AAPL", "x")  # skipped
    reporter.ticker(4, 10, "AAPL", "x")  # emitted
    reporter.end_ticker()
    events = await _drain(queue)
    ticker_events = [e for e in events if e["type"] == "ticker"]
    assert len(ticker_events) == 2
    assert events[-1]["type"] == "ticker_end"


@pytest.mark.asyncio
async def test_ticker_no_throttle_emits_all():
    queue: asyncio.Queue = asyncio.Queue()
    reporter = EventReporter(queue, asyncio.get_running_loop())
    reporter.begin_ticker(3, "Resolving")
    reporter.ticker(1, 3, "AAPL", "x")
    reporter.ticker(2, 3, "AAPL", "x")
    reporter.ticker(3, 3, "AAPL", "x")
    events = await _drain(queue)
    assert len([e for e in events if e["type"] == "ticker"]) == 3


@pytest.mark.asyncio
async def test_end_ticker_idempotent():
    queue: asyncio.Queue = asyncio.Queue()
    reporter = EventReporter(queue, asyncio.get_running_loop())
    reporter.end_ticker()  # no ticker started — must not raise
    assert await _drain(queue) == [{"type": "ticker_end"}]


@pytest.mark.asyncio
async def test_console_shim_emits():
    queue: asyncio.Queue = asyncio.Queue()
    reporter = EventReporter(queue, asyncio.get_running_loop())
    reporter.console.print("some table")
    events = await _drain(queue)
    assert events == [{"type": "console", "text": "some table"}]
