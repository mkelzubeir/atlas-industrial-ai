"""Authentication boundary for the agent-facing API.

This is deliberately modest: a shared secret in a header, compared in constant
time. It is not production authentication and the README says so plainly.

What it *does* demonstrate is the boundary itself. The ElevenLabs webhook tools
run server-side on ElevenLabs' infrastructure and call this API over the public
internet, so "anyone who finds the URL can mutate orders" is a real exposure
even for a demo. A single shared secret is the smallest thing that closes it.

A production version of this would carry a per-caller identity, scope tokens to
specific customers so one caller cannot read another's orders, and verify a
signed request rather than a bearer secret.
"""

from __future__ import annotations

import secrets

from fastapi import Header, status

from app.config import get_settings
from app.errors import AtlasError, ErrorCode

API_KEY_HEADER = "X-Atlas-Api-Key"


async def require_api_key(x_atlas_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency guarding every `/api` route.

    When no key is configured the check is skipped entirely, so `uvicorn` with
    no environment at all still runs for local development.
    """
    expected = get_settings().api_key
    if not expected:
        return

    if not x_atlas_api_key or not secrets.compare_digest(x_atlas_api_key, expected):
        raise AtlasError(
            ErrorCode.UNAUTHORIZED,
            "This request was not authorised.",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )


async def require_demo_mode() -> None:
    """Guards endpoints that must never exist outside a demo deployment."""
    if not get_settings().demo_mode:
        raise AtlasError(
            ErrorCode.DEMO_MODE_DISABLED,
            "Demo endpoints are disabled on this deployment.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
