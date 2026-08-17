"""Runtime control primitives shared by the graph walker and search agents.

The walker runs in a worker thread (``asyncio.to_thread``) while the HTTP
control endpoint runs on the event loop, so control objects are thread-safe
and expose a blocking ``checkpoint`` callable the search agents call at
per-symbol boundaries (drain-then-freeze). ``RunCancelled`` is the
cooperative cancel signal both layers understand; ``register_control`` /
``get_control`` plumb a control object into a JSON-safe ``__control_id__``
token so a tool callable can recover it without touching the persisted
``params``/``node_overrides`` JSON.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any, Callable, Optional


class RunCancelled(Exception):
    """Cooperative cancel: raised at the next checkpoint once cancel is armed."""


_CONTROL_REGISTRY: dict[str, Any] = {}
_CONTROL_LOCK = threading.Lock()
_CONTROL_IDS = itertools.count()


def register_control(control: Any) -> str:
    """Store ``control`` and return a fresh opaque token (its ``__control_id__``)."""
    with _CONTROL_LOCK:
        cid = str(next(_CONTROL_IDS))
        _CONTROL_REGISTRY[cid] = control
        return cid


def get_control(control_id: Optional[str]) -> Optional[Any]:
    """Look up a control object by token (None when unknown or unset)."""
    if not control_id:
        return None
    with _CONTROL_LOCK:
        return _CONTROL_REGISTRY.get(control_id)


def unregister_control(control_id: Optional[str]) -> None:
    """Drop a control object (called when a run finishes to avoid leaks)."""
    if not control_id:
        return
    with _CONTROL_LOCK:
        _CONTROL_REGISTRY.pop(control_id, None)


def checkpoint_for(control_id: Optional[str]) -> Optional[Callable[[], None]]:
    """Build the per-symbol ``checkpoint`` callable for a token (or None)."""
    control = get_control(control_id)
    if control is None:
        return None
    return control.checkpoint


__all__ = [
    "RunCancelled",
    "checkpoint_for",
    "get_control",
    "register_control",
    "unregister_control",
]
