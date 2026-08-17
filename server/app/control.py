"""Thread-safe per-run control state (skip / pause / resume / cancel / confirm).

The graph walker runs in a worker thread while the control endpoint runs on
the event loop, so all mutable state is guarded by ``threading.Lock`` /
``threading.Event``. ``checkpoint()`` is the blocking callable the search
agents call at per-symbol boundaries: it returns immediately while running,
freezes (drains in-flight symbols) while paused, and raises ``RunCancelled``
once cancel is armed.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from stock_analyze.tools.control import RunCancelled

CONFIRM_DECISIONS = ("proceed", "skip", "cancel")


class RunControl:
    """One mutable control object per in-flight graph run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._paused = threading.Event()
        self._cancel = threading.Event()
        self._skip: set[str] = set()
        self._confirm_events: dict[str, threading.Event] = {}
        self._confirm_state: dict[str, dict[str, Any]] = {}
        self._pending: Optional[str] = None

    # ── skip ─────────────────────────────────────────────────────────

    def arm_skip(self, node_id: str) -> None:
        with self._lock:
            self._skip.add(node_id)

    def is_skipped(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._skip

    def skipped_nodes(self) -> list[str]:
        with self._lock:
            return sorted(self._skip)

    # ── pause / resume ───────────────────────────────────────────────

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    # ── cancel ───────────────────────────────────────────────────────

    def cancel(self) -> None:
        self._cancel.set()
        # A pending confirmation gate must also resolve so the blocked worker
        # thread wakes up and sees the cancel.
        with self._lock:
            for node_id in list(self._confirm_events):
                self._confirm_state.setdefault(node_id, {})["decision"] = "cancel"
                self._confirm_events[node_id].set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # ── checkpoint (drain-then-freeze) ───────────────────────────────

    def checkpoint(self) -> None:
        """Block while paused; raise ``RunCancelled`` once cancelled."""
        self._raise_if_cancelled()
        while self._paused.is_set():
            self._raise_if_cancelled()
            self._paused.wait(timeout=0.1)
        self._raise_if_cancelled()

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise RunCancelled()

    # ── confirmation gate ────────────────────────────────────────────

    def request_confirmation(
        self, node_id: str, symbol_count: int, tavily_estimate: int
    ) -> None:
        evt = threading.Event()
        with self._lock:
            self._confirm_events[node_id] = evt
            self._confirm_state[node_id] = {
                "decision": None,
                "symbol_count": symbol_count,
                "tavily_estimate": tavily_estimate,
            }
            self._pending = node_id

    def wait_confirmation(self, node_id: str) -> Optional[str]:
        """Block until a decision arrives; return ``proceed|skip|cancel``."""
        evt = self._confirm_events.get(node_id)
        if evt is None:
            return None
        evt.wait()
        with self._lock:
            return (self._confirm_state.get(node_id) or {}).get("decision")

    def confirm(self, node_id: str, decision: str) -> None:
        with self._lock:
            evt = self._confirm_events.get(node_id)
            if evt is None:
                return
            self._confirm_state.setdefault(node_id, {})["decision"] = decision
            evt.set()
            if self._pending == node_id:
                self._pending = None

    def pending_confirmation(self) -> Optional[dict[str, Any]]:
        """The node awaiting confirmation, or None (for dashboard/run detail)."""
        with self._lock:
            if self._pending is None:
                return None
            state = self._confirm_state.get(self._pending) or {}
            return {
                "node_id": self._pending,
                "symbol_count": state.get("symbol_count"),
                "tavily_estimate": state.get("tavily_estimate"),
            }


__all__ = ["CONFIRM_DECISIONS", "RunControl"]
