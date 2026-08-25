#!/usr/bin/env python3
"""Provision the Atlas agent, its webhook tools and its API-key secret.

Configuration-as-code for the ElevenLabs side of the deployment. The agent's
prompt, tool schemas and settings live in version control (`agent/prompt.md`,
`agent/tools.json`, `agent/agent.json`) and this script reconciles the platform
to match them.

That is the point: clicking an agent together in a dashboard leaves no record of
why a tool description says what it says. Here, tuning a description is a diff.

The script is **idempotent** -- it looks resources up by name and updates them
rather than creating duplicates, so it is safe to re-run after every prompt
tweak.

Usage
-----
    export ELEVENLABS_API_KEY=...          # ElevenLabs key with agents access
    export ATLAS_PUBLIC_BASE_URL=https://<tunnel>.ngrok-free.app
    export ATLAS_API_KEY=...               # shared secret the backend expects

    python scripts/provision_agent.py --dry-run    # show the plan
    python scripts/provision_agent.py              # apply it

Only the standard library is used, so this runs under any Python 3.11+ with no
virtualenv.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO_ROOT / "agent"
API_BASE = "https://api.elevenlabs.io"

SECRET_NAME = "ATLAS_API_KEY"
AGENT_ID_FILE = AGENT_DIR / ".agent-id"


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


# ---------------------------------------------------------------------------
# Local configuration
# ---------------------------------------------------------------------------

def load_local_config() -> tuple[str, list[dict], dict]:
    prompt_path = AGENT_DIR / "prompt.md"
    tools_path = AGENT_DIR / "tools.json"
    agent_path = AGENT_DIR / "agent.json"

    for path in (prompt_path, tools_path, agent_path):
        if not path.exists():
            raise ProvisioningError(f"Missing required file: {path}")

    return (
        prompt_path.read_text(encoding="utf-8"),
        json.loads(tools_path.read_text(encoding="utf-8")),
        json.loads(agent_path.read_text(encoding="utf-8")),
    )


def render_tools(tools: list[dict], base_url: str, secret_id: str) -> list[dict]:
    """Substitute deployment-specific values into the versioned tool schemas."""
    rendered = json.dumps(tools)
    rendered = rendered.replace("__BASE_URL__", base_url.rstrip("/"))
    rendered = rendered.replace("__SECRET_ID__", secret_id)
    return json.loads(rendered)


def validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "https":
        raise ProvisioningError(
            f"ATLAS_PUBLIC_BASE_URL must be https, got {base_url!r}. "
            "ElevenLabs calls your webhooks over the public internet."
        )
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise ProvisioningError(
            f"{base_url!r} is not reachable from ElevenLabs' servers. "
            "Expose the backend with a tunnel (e.g. `ngrok http 8000`) and use that URL."
        )
    return base_url.rstrip("/")


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def ensure_secret(client: ElevenLabsClient, atlas_api_key: str) -> str:
    """Find or create the workspace secret holding the backend's shared key.

    Existing secrets are reused rather than rotated: their values cannot be read
    back, so silently replacing one would break any other agent using it.
    """
    Out.step(f"Workspace secret {SECRET_NAME!r}")

    for secret in client.list_secrets():
        if secret.get("name") == SECRET_NAME:
            secret_id = secret.get("secret_id") or secret.get("id")
            Out.same(f"already exists ({secret_id})")
            Out.warn(
                "Existing secret reused. If you rotated ATLAS_API_KEY, delete the "
                "secret in the ElevenLabs dashboard and re-run."
            )
            return secret_id

    if not atlas_api_key:
        raise ProvisioningError(
            "ATLAS_API_KEY is not set, so the webhook tools would call your backend "
            "unauthenticated. Set it (in backend/.env and this environment) and re-run."
        )

    created = client.create_secret(SECRET_NAME, atlas_api_key)
    secret_id = created.get("secret_id") or created.get("id")
    Out.ok(f"created ({secret_id})")
    return secret_id


def reconcile_tools(client: ElevenLabsClient, tools: list[dict]) -> list[str]:
    Out.step(f"Webhook tools ({len(tools)})")

    existing = {}
    for tool in client.list_tools():
        name = (tool.get("tool_config") or {}).get("name") or tool.get("name")
        if name:
            existing[name] = tool.get("id") or tool.get("tool_id")

    tool_ids: list[str] = []
    for tool_config in tools:
        name = tool_config["name"]
        if name in existing:
            tool_id = existing[name]
            client.update_tool(tool_id, tool_config)
            Out.ok(f"{name:<20} updated ({tool_id})")
        else:
            created = client.create_tool(tool_config)
            tool_id = created.get("id") or created.get("tool_id")
            Out.ok(f"{name:<20} created ({tool_id})")
        tool_ids.append(tool_id)

    return tool_ids


def build_agent_payload(
    agent_config: dict, prompt: str, tool_ids: list[str], llm: str | None, voice_id: str | None
) -> dict:
    payload = json.loads(json.dumps(agent_config))  # deep copy

    conversation_config = payload.setdefault("conversation_config", {})
    agent = conversation_config.setdefault("agent", {})
    prompt_config = agent.setdefault("prompt", {})

    prompt_config["prompt"] = prompt
    prompt_config["tool_ids"] = tool_ids
    if llm:
        prompt_config["llm"] = llm

    if voice_id:
        conversation_config.setdefault("tts", {})["voice_id"] = voice_id

    return payload


def reconcile_agent(client: ElevenLabsClient, payload: dict) -> str:
    name = payload.get("name", "Atlas Industrial Supply")
    Out.step(f"Agent {name!r}")

    # Prefer the id recorded by a previous run; fall back to matching on name.
    recorded_id = AGENT_ID_FILE.read_text().strip() if AGENT_ID_FILE.exists() else None
    agent_id = None

    agents = client.list_agents()
    by_id = {a.get("agent_id"): a for a in agents}
    if recorded_id and recorded_id in by_id:
        agent_id = recorded_id
    else:
        for agent in agents:
            if agent.get("name") == name:
                agent_id = agent.get("agent_id")
                break

    if agent_id:
        client.update_agent(agent_id, payload)
        Out.ok(f"updated ({agent_id})")
    else:
        created = client.create_agent(payload)
        agent_id = created.get("agent_id")
        Out.ok(f"created ({agent_id})")

    if not client.dry_run and agent_id:
        AGENT_ID_FILE.write_text(agent_id + "\n")
        Out.same(f"agent id written to {AGENT_ID_FILE.relative_to(REPO_ROOT)}")

    return agent_id


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ATLAS_PUBLIC_BASE_URL", ""),
        help="Public HTTPS base URL of the Atlas backend, as reachable from ElevenLabs.",
    )
    parser.add_argument("--api-key", default=os.environ.get("ELEVENLABS_API_KEY", ""))
    parser.add_argument("--atlas-api-key", default=os.environ.get("ATLAS_API_KEY", ""))
    parser.add_argument("--llm", default=os.environ.get("ATLAS_AGENT_LLM", ""),
                        help="Override the agent LLM. Omit to use the platform default.")
    parser.add_argument("--voice-id", default=os.environ.get("ATLAS_AGENT_VOICE_ID", ""),
                        help="Override the agent voice. Omit to use the platform default.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the plan without calling the ElevenLabs API.")
    args = parser.parse_args()

    try:
        if not args.api_key and not args.dry_run:
            raise ProvisioningError(
                "ELEVENLABS_API_KEY is not set. Export it or pass --api-key."
            )
        base_url = validate_base_url(args.base_url) if args.base_url else None
        if base_url is None:
            raise ProvisioningError(
                "ATLAS_PUBLIC_BASE_URL is not set. Start a tunnel to your backend "
                "(e.g. `ngrok http 8000`) and export its https URL."
            )

        prompt, tools, agent_config = load_local_config()

        print()
        Out.step("Plan")
        Out.same(f"backend base URL : {base_url}")
        Out.same(f"prompt           : {len(prompt.splitlines())} lines")
        Out.same(f"tools            : {', '.join(t['name'] for t in tools)}")
        Out.same(f"llm              : {args.llm or 'platform default'}")
        Out.same(f"voice            : {args.voice_id or 'platform default'}")
        if args.dry_run:
            Out.warn("dry run -- no API calls will be made")
        print()

        client = ElevenLabsClient(args.api_key or "dry-run", dry_run=args.dry_run)

        secret_id = ensure_secret(client, args.atlas_api_key)
        rendered_tools = render_tools(tools, base_url, secret_id)
        tool_ids = reconcile_tools(client, rendered_tools)
        payload = build_agent_payload(
            agent_config, prompt, tool_ids, args.llm or None, args.voice_id or None
        )
        agent_id = reconcile_agent(client, payload)

        print()
        Out.step("Done")
        Out.ok(f"agent_id = {agent_id}")
        print()
        print("  Next: put this in frontend/.env.local and start the frontend.")
        print(f"    NEXT_PUBLIC_ELEVENLABS_AGENT_ID={agent_id}")
        print()
        return 0

    except ProvisioningError as exc:
        print()
        Out.fail(str(exc))
        print()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
