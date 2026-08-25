"""Structured JSON logging.

Every tool call the agent makes lands here as one line of JSON, which is what
makes a conversation explainable after the fact: given a conversation id you can
reconstruct exactly which tools ran, with which arguments, and what came back.

Secrets are never logged -- the auth header is stripped before a request is
recorded.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services import activity

#: Correlates every log line emitted while handling one request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

#: The ElevenLabs conversation id, when the agent passes one through.
conversation_id_var: ContextVar[str | None] = ContextVar("conversation_id", default=None)

#: Per-request holder that a route fills in via `log_event("tool.<name>", ...)`
#: so the middleware can attach the tool name and arguments to its activity
#: record.
#:
#: This is a *mutable dict* rather than a value the route re-sets, and that is
#: deliberate. `BaseHTTPMiddleware` runs the downstream app in a separate task,
#: so a `ContextVar.set()` inside a route handler is invisible to the
#: middleware afterwards. Setting the variable once here and mutating the dict
#: the route shares a reference to sidesteps that entirely.
tool_context_var: ContextVar[dict | None] = ContextVar("tool_context", default=None)

SENSITIVE_HEADERS = {"x-atlas-api-key", "authorization", "cookie", "xi-api-key"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        conversation_id = conversation_id_var.get()
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Anything passed via logger.info(..., extra={"context": {...}}).
        context = getattr(record, "context", None)
        if context:
            payload["context"] = context
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn's own access log would duplicate our structured entries.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


logger = logging.getLogger("atlas")


def log_event(message: str, **context: Any) -> None:
    """Emit one structured line.

    A message beginning with `tool.` also stashes its context for the request
    middleware, which is what puts tool arguments in front of the Developer
    View. One call site, two outputs.
    """
    if message.startswith("tool."):
        holder = tool_context_var.get()
        if holder is not None:
            holder["tool"] = message.removeprefix("tool.")
            holder["params"] = dict(context)
    logger.info(message, extra={"context": context})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, and logs the outcome."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_var.set(request_id)
        # The agent forwards its conversation id so backend logs can be joined
        # to the ElevenLabs transcript for the same call.
        conversation_id_var.set(request.headers.get("x-conversation-id"))

        # Shared with the route handler; see the note on tool_context_var.
        tool_context: dict = {}
        tool_context_var.set(tool_context)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "context": {
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "request",
            extra={
                "context": {
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query) or None,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        # Record the call for the Developer View. Only business endpoints --
        # health probes and the demo control plane are not tool calls.
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/demo"):
            activity.record(
                tool=tool_context.get("tool"),
                method=request.method,
                path=request.url.path,
                query=str(request.url.query) or None,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                conversation_id=request.headers.get("x-conversation-id"),
                params=tool_context.get("params"),
                error_code=getattr(request.state, "atlas_error_code", None),
            )

        response.headers["x-request-id"] = request_id
        return response
