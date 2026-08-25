"""Shared route dependencies."""

from __future__ import annotations

import asyncio

from fastapi import status

from app.errors import AtlasError, ErrorCode
from app.services import faults


def fault_gate(target: str):
    """Build a dependency that fails this endpoint when a fault is armed.

    Used only by the demo/eval harness. In the normal case `consume` returns
    None and the dependency is a no-op.
    """

    async def _gate() -> None:
        mode = faults.consume(target)
        if mode is None:
            return
        if mode == "timeout":
            await asyncio.sleep(8)
        raise AtlasError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The Atlas system for that request is temporarily unavailable. "
            "I can't retrieve that information right now.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"target": target},
        )

    return _gate
