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

#: Correlates every log line emitted while handling one request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

#: The ElevenLabs conversation id, when the agent passes one through.
conversation_id_var: ContextVar[str | None] = ContextVar("conversation_id", default=None)

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
    """Emit one structured line. Used by the tool endpoints."""
    logger.info(message, extra={"context": context})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, and logs the outcome."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_var.set(request_id)
        # The agent forwards its conversation id so backend logs can be joined
        # to the ElevenLabs transcript for the same call.
        conversation_id_var.set(request.headers.get("x-conversation-id"))

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
        response.headers["x-request-id"] = request_id
        return response
