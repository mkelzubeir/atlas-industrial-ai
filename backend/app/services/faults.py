"""Deliberate fault injection, for demonstrating failure handling.

One of the evaluation scenarios requires the backend to fail on purpose so the
agent's behaviour under a broken tool can be observed: does it say it cannot
retrieve the information, or does it invent an answer?

Making that reproducible needs a switch. This is it. The state is a plain
in-memory counter -- it resets when the process restarts, and the endpoints that
arm it are demo-gated.
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_armed: dict[str, dict[str, Any]] = {}

VALID_TARGETS = frozenset({"orders", "products", "inventory", "shipments", "rfqs", "customers", "all"})


def arm(target: str, calls: int = 1, mode: str = "error") -> dict[str, Any]:
    with _lock:
        _armed[target] = {"target": target, "remaining": calls, "mode": mode}
        return dict(_armed[target])


def clear() -> None:
    with _lock:
        _armed.clear()


def status() -> dict[str, Any]:
    with _lock:
        return {key: dict(value) for key, value in _armed.items()}


def consume(target: str) -> str | None:
    """Return the fault mode if this call should fail, decrementing the counter."""
    with _lock:
        for key in (target, "all"):
            entry = _armed.get(key)
            if entry and entry["remaining"] > 0:
                entry["remaining"] -= 1
                mode = entry["mode"]
                if entry["remaining"] <= 0:
                    _armed.pop(key, None)
                return mode
    return None
