"""Shared helpers for the ElevenLabs provisioning and evaluation scripts.

A deliberately small REST client over the standard library, so both scripts run
under any Python 3.11+ with no virtualenv and no third-party dependencies.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.elevenlabs.io"


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def _supports_colour() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


class Out:
    _C = _supports_colour()

    @classmethod
    def _p(cls, colour: str, prefix: str, message: str) -> None:
        if cls._C:
            print(f"\033[{colour}m{prefix}\033[0m {message}")
        else:
            print(f"{prefix} {message}")

    @classmethod
    def step(cls, message: str) -> None:
        cls._p("1;34", "==>", message)

    @classmethod
    def ok(cls, message: str) -> None:
        cls._p("32", "  +", message)

    @classmethod
    def same(cls, message: str) -> None:
        cls._p("90", "  =", message)

    @classmethod
    def warn(cls, message: str) -> None:
        cls._p("33", "  !", message)

    @classmethod
    def fail(cls, message: str) -> None:
        cls._p("31", "  x", message)


class ProvisioningError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Minimal ElevenLabs REST client
# ---------------------------------------------------------------------------

class ElevenLabsClient:
    """Just enough of the ElevenLabs API to provision an agent."""

    def __init__(self, api_key: str, *, dry_run: bool = False) -> None:
        self.api_key = api_key
        self.dry_run = dry_run

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{API_BASE}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("xi-api-key", self.api_key)
        request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read().decode()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            try:
                detail = json.dumps(json.loads(detail), indent=2)[:1200]
            except json.JSONDecodeError:
                detail = detail[:1200]
            raise ProvisioningError(
                f"{method} {path} failed with HTTP {exc.code}.\n{detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProvisioningError(
                f"{method} {path} could not reach {API_BASE}: {exc.reason}"
            ) from exc

    # -- reads ------------------------------------------------------------
    def _read(self, path: str, key: str) -> list[dict]:
        """Read a collection.

        Under --dry-run an unreachable API is not fatal: the plan is still
        worth printing, so the read degrades to "nothing exists yet" with a
        warning rather than aborting.
        """
        try:
            return self._request("GET", path).get(key, [])
        except ProvisioningError:
            if self.dry_run:
                Out.warn(f"could not read {key} (offline); assuming none exist")
                return []
            raise

    def list_secrets(self) -> list[dict]:
        return self._read("v1/convai/secrets", "secrets")

    def list_tools(self) -> list[dict]:
        return self._read("v1/convai/tools", "tools")

    def list_agents(self) -> list[dict]:
        return self._read("v1/convai/agents", "agents")

    # -- writes -----------------------------------------------------------
    def create_secret(self, name: str, value: str) -> dict:
        if self.dry_run:
            return {"secret_id": "<dry-run-secret-id>", "name": name}
        return self._request("POST", "v1/convai/secrets", {"name": name, "value": value})

    def create_tool(self, tool_config: dict) -> dict:
        if self.dry_run:
            return {"id": f"<dry-run-{tool_config['name']}>"}
        return self._request("POST", "v1/convai/tools", {"tool_config": tool_config})

    def update_tool(self, tool_id: str, tool_config: dict) -> dict:
        if self.dry_run:
            return {"id": tool_id}
        return self._request(
            "PATCH", f"v1/convai/tools/{tool_id}", {"tool_config": tool_config}
        )

    def create_agent(self, payload: dict) -> dict:
        if self.dry_run:
            return {"agent_id": "<dry-run-agent-id>"}
        return self._request("POST", "v1/convai/agents/create", payload)

    def update_agent(self, agent_id: str, payload: dict) -> dict:
        if self.dry_run:
            return {"agent_id": agent_id}
        return self._request("PATCH", f"v1/convai/agents/{agent_id}", payload)

    # -- agent tests ------------------------------------------------------
    def list_tests(self) -> list[dict]:
        return self._read("v1/convai/agent-testing", "tests")

    def create_test(self, body: dict) -> dict:
        if self.dry_run:
            return {"id": f"<dry-run-{body.get('name', 'test')}>"}
        return self._request("POST", "v1/convai/agent-testing/create", body)

    def update_test(self, test_id: str, body: dict) -> dict:
        if self.dry_run:
            return {"id": test_id}
        return self._request("PUT", f"v1/convai/agent-testing/{test_id}", body)

    def run_tests(self, agent_id: str, test_ids: list[str]) -> dict:
        if self.dry_run:
            return {"id": "<dry-run-invocation>", "test_runs": []}
        return self._request(
            "POST",
            f"v1/convai/agents/{agent_id}/run-tests",
            {"tests": [{"test_id": test_id} for test_id in test_ids]},
        )

    def get_invocation(self, invocation_id: str) -> dict:
        return self._request("GET", f"v1/convai/test-invocations/{invocation_id}")
