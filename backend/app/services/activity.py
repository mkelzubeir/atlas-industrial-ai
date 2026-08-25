"""In-memory ring buffer of recent tool calls, for the Developer View.

The ElevenLabs client SDK reports which tool ran and what came back, but not
the *arguments* the agent chose. Those only exist on this side of the wire, so
the backend keeps a short rolling record of them.

Entries are keyed by the conversation id the agent forwards in
`X-Conversation-Id`, which is what lets the UI line a backend call up with the
turn of conversation that caused it.

Deliberately in-memory and bounded: this is demo observability, not an audit
log. Writes that change business state are recorded durably in `audit_events`.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

MAX_ENTRIES = 200

#: Route -> tool name, used when a request fails before the handler logs.
#: A refused write is the most interesting row in the Developer View, so it
#: must not be the one that shows up unlabelled.
_TOOL_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("PATCH", "/lines/", "update_order_line"),
    ("GET", "/shipments", "lookup_shipment"),
    ("GET", "/api/orders/", "lookup_order"),
    ("GET", "/api/products/search", "search_products"),
    ("GET", "/api/inventory/", "check_inventory"),
    ("GET", "/api/customers/search", "search_customer"),
    ("POST", "/api/rfqs", "create_rfq"),
    ("GET", "/api/rfqs/", "lookup_rfq"),
)


def tool_for(method: str, path: str) -> str | None:
    """Best-effort tool name for a request, from its method and path."""
    for wanted_method, fragment, tool in _TOOL_ROUTES:
        if method == wanted_method and fragment in path:
            return tool
    return None

_lock = threading.Lock()
_entries: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
_counter = 0


def record(
    *,
    tool: str | None,
    method: str,
    path: str,
    query: str | None,
    status_code: int,
    duration_ms: float,
    request_id: str,
    conversation_id: str | None,
    params: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    global _counter
    with _lock:
        _counter += 1
        _entries.append(
            {
                "seq": _counter,
                "timestamp": datetime.now(UTC).isoformat(),
                "tool": tool,
                "method": method,
                "path": path,
                "query": query,
                "status_code": status_code,
                "ok": 200 <= status_code < 300,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "conversation_id": conversation_id,
                "params": params or {},
                "error_code": error_code,
            }
        )


def recent(
    conversation_id: str | None = None, limit: int = 50, since_seq: int = 0
) -> list[dict[str, Any]]:
    with _lock:
        entries = list(_entries)

    if conversation_id:
        entries = [e for e in entries if e["conversation_id"] == conversation_id]
    if since_seq:
        entries = [e for e in entries if e["seq"] > since_seq]
    return entries[-limit:]


def clear() -> None:
    with _lock:
        _entries.clear()
