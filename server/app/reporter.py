"""EventReporter — a RunProgress duck-type that streams scan events to a queue.

The stock_analyze pipeline calls reporter methods from a worker thread
(``asyncio.to_thread``), so events are marshalled onto the event loop with
``loop.call_soon_threadsafe`` rather than mutating an asyncio.Queue directly.
"""

from __future__ import annotations

import asyncio
from typing import Any


class _ConsoleShim:
    """Minimal ``console`` shim: the pipeline calls ``reporter.console.print(...)``."""

    def __init__(self, emit: Any) -> None:
        self._emit = emit

    def print(self, text: Any = "", *args: Any, **kwargs: Any) -> None:
        self._emit("console", text=str(text))


class EventReporter:
    """Duck-types ``stock_analyze.progress.RunProgress``.

    Emits JSON events: ``stage``, ``stage_done``, ``fail``, ``ticker_begin``,
    ``ticker``, ``ticker_end``, and ``console`` (via the ``console`` shim).
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self._queue = queue
        self._loop = loop
        self._throttle = 0
        self._ticker_count = 0
        self.console = _ConsoleShim(self._emit)

    def _emit(self, event_type: str, **fields: Any) -> None:
        event = {"type": event_type, **fields}
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # Event loop closed during shutdown; drop the event.
            pass

    def stage(self, text: str) -> None:
        self._emit("stage", text=text)

    def stage_done(self, text: str) -> None:
        self._emit("stage_done", text=text)

    def fail(self, text: str) -> None:
        self._emit("fail", text=text)

    def begin_ticker(self, total: int, description: str, throttle: int = 0) -> None:
        self._throttle = throttle
        self._ticker_count = 0
        self._emit("ticker_begin", total=total, description=description)

    def ticker(self, index: int, total: int, symbol: str, action: str) -> None:
        self._ticker_count += 1
        if self._throttle > 0 and self._ticker_count % self._throttle != 0 and index < total:
            return
        self._emit("ticker", index=index, total=total, symbol=symbol, action=action)

    def end_ticker(self) -> None:
        self._emit("ticker_end")
        self._throttle = 0
        self._ticker_count = 0
