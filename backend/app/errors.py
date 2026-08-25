"""Structured error contract shared by every endpoint.

Why this exists as its own module: the voice agent is a consumer of this API
just like any other client, and it needs errors it can *explain to a caller*.
A bare FastAPI 422 or a stack trace gives the model nothing to say. Every
failure therefore comes back in one shape:

    {"error": {"code": "ORDER_NOT_MODIFIABLE",
               "message": "Purchase order 1260 has already shipped.",
               "details": {...}}}

`code` is the stable, machine-readable contract (tests assert on it).
`message` is written to be spoken almost verbatim by the agent.
`details` carries structured context the agent can use to ask a better question
-- for example the candidate products behind an AMBIGUOUS_PRODUCT error.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode:
    """Stable error codes. Treated as an API contract, not an implementation detail."""

    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    AMBIGUOUS_PRODUCT = "AMBIGUOUS_PRODUCT"
    INSUFFICIENT_INVENTORY = "INSUFFICIENT_INVENTORY"
    ORDER_NOT_MODIFIABLE = "ORDER_NOT_MODIFIABLE"
    LINE_NOT_MODIFIABLE = "LINE_NOT_MODIFIABLE"
    LINE_NOT_FOUND = "LINE_NOT_FOUND"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    QUANTITY_INCREASE_NOT_ALLOWED = "QUANTITY_INCREASE_NOT_ALLOWED"
    CUSTOMER_MISMATCH = "CUSTOMER_MISMATCH"
    RFQ_NOT_FOUND = "RFQ_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    DEMO_MODE_DISABLED = "DEMO_MODE_DISABLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class AtlasError(Exception):
    """Raised anywhere in the app to produce a structured error response."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return {"error": body}


def not_found(code: str, message: str, **details: Any) -> AtlasError:
    return AtlasError(code, message, http_status=status.HTTP_404_NOT_FOUND, details=details or None)


def conflict(code: str, message: str, **details: Any) -> AtlasError:
    return AtlasError(code, message, http_status=status.HTTP_409_CONFLICT, details=details or None)


def bad_request(code: str, message: str, **details: Any) -> AtlasError:
    return AtlasError(
        code, message, http_status=status.HTTP_400_BAD_REQUEST, details=details or None
    )


async def atlas_error_handler(request: Request, exc: AtlasError) -> JSONResponse:
    # Surfaced to the request middleware so the Developer View can show *why*
    # a call failed, not merely that it returned a non-200.
    request.state.atlas_error_code = exc.code
    return JSONResponse(status_code=exc.http_status, content=exc.to_payload())


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Reshape FastAPI's default 422 body into the Atlas error envelope.

    Without this, malformed tool arguments would reach the agent in a completely
    different shape from every other error, and the prompt would need to know
    about two formats.
    """
    request.state.atlas_error_code = ErrorCode.VALIDATION_ERROR
    problems = [
        {"field": ".".join(str(p) for p in err.get("loc", []) if p != "body"), "issue": err.get("msg", "")}
        for err in exc.errors()
    ]
    summary = "; ".join(f"{p['field']}: {p['issue']}" for p in problems if p["field"]) or "Invalid request."
    return JSONResponse(
        status_code=422,  # Unprocessable Content
        content={
            "error": {
                "code": ErrorCode.VALIDATION_ERROR,
                "message": f"The request was not valid. {summary}",
                "details": {"problems": problems},
            }
        },
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Last-resort handler.

    Deliberately leaks nothing about the internals: the agent gets a sentence it
    can say out loud, and the traceback stays in the server log.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR,
                "message": "Atlas systems are temporarily unavailable. Please try again shortly.",
            }
        },
    )
