"""Validate the versioned agent configuration.

The ElevenLabs API cannot be called from CI, so these tests pin the parts of
the tool schemas that would otherwise only fail at provisioning time -- or,
worse, mid-conversation.

Two classes of bug they catch:

1. **Drift between the tools and the backend.** Every tool URL is checked
   against the routes FastAPI actually exposes, so renaming an endpoint without
   updating the tool definition fails here rather than silently 404-ing during
   a demo.

2. **Silent-failure settings.** `tool_error_handling_mode` defaults to hiding
   errors from the agent, which would leave it unable to explain why a change
   was refused. Every tool must opt into `passthrough`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.main import app

AGENT_DIR = Path(__file__).resolve().parents[2] / "agent"

# Mirrors LiteralJsonSchemaPropertyType in the ElevenLabs SDK.
ALLOWED_PARAM_TYPES = {"boolean", "string", "integer", "number"}
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

EXPECTED_TOOLS = {
    "lookup_order",
    "lookup_shipment",
    "search_products",
    "check_inventory",
    "search_customer",
    "create_rfq",
    "update_order_line",
}


@pytest.fixture(scope="module")
def tools() -> list[dict]:
    return json.loads((AGENT_DIR / "tools.json").read_text())


@pytest.fixture(scope="module")
def backend_paths() -> set[str]:
    return set(app.openapi()["paths"])


def test_all_expected_tools_are_defined(tools):
    assert {tool["name"] for tool in tools} == EXPECTED_TOOLS


def test_tool_urls_match_real_backend_routes(tools, backend_paths):
    """Catches a renamed endpoint before it breaks a live call."""
    for tool in tools:
        url = tool["api_schema"]["url"]
        assert url.startswith("__BASE_URL__/"), tool["name"]
        path = url.replace("__BASE_URL__", "")
        assert path in backend_paths, f"{tool['name']} points at unknown route {path}"


def test_tool_methods_match_backend_methods(tools, backend_paths):
    spec = app.openapi()["paths"]
    for tool in tools:
        path = tool["api_schema"]["url"].replace("__BASE_URL__", "")
        method = tool["api_schema"]["method"]
        assert method in ALLOWED_METHODS
        assert method.lower() in spec[path], (
            f"{tool['name']} uses {method} but {path} does not accept it"
        )


def test_every_tool_passes_errors_through_to_the_agent(tools):
    """Without this the agent cannot explain a refusal -- it never sees it."""
    for tool in tools:
        assert tool["tool_error_handling_mode"] == "passthrough", tool["name"]


def test_every_tool_is_authenticated_and_traceable(tools):
    for tool in tools:
        headers = tool["api_schema"]["request_headers"]
        assert headers["X-Atlas-Api-Key"] == {"secret_id": "__SECRET_ID__"}, tool["name"]
        # Lets a backend log line be joined to the ElevenLabs transcript.
        assert headers["X-Conversation-Id"] == {
            "variable_name": "system__conversation_id"
        }, tool["name"]


def test_no_secret_value_is_committed(tools):
    """The repo must reference the secret by id, never carry its value."""
    raw = (AGENT_DIR / "tools.json").read_text()
    assert "__SECRET_ID__" in raw
    for tool in tools:
        header = tool["api_schema"]["request_headers"]["X-Atlas-Api-Key"]
        assert isinstance(header, dict) and "secret_id" in header


def test_parameter_types_are_valid_for_the_platform(tools):
    def check(schema: dict, label: str) -> None:
        for name, prop in (schema.get("properties") or {}).items():
            kind = prop.get("type")
            if kind == "object":
                check(prop, f"{label}.{name}")
            elif kind == "array":
                check(prop.get("items", {}), f"{label}.{name}[]")
            else:
                assert kind in ALLOWED_PARAM_TYPES, f"{label}.{name} has type {kind!r}"

    for tool in tools:
        schema = tool["api_schema"]
        for path_param, prop in (schema.get("path_params_schema") or {}).items():
            assert prop["type"] in ALLOWED_PARAM_TYPES, f"{tool['name']}.{path_param}"
        if "query_params_schema" in schema:
            check(schema["query_params_schema"], f"{tool['name']}.query")
        if "request_body_schema" in schema:
            check(schema["request_body_schema"], f"{tool['name']}.body")


def test_every_parameter_is_described_for_the_model(tools):
    """A parameter with no description is one the model has to guess at."""

    def check(schema: dict, label: str) -> None:
        for name, prop in (schema.get("properties") or {}).items():
            assert prop.get("description"), f"{label}.{name} has no description"
            if prop.get("type") == "object":
                check(prop, f"{label}.{name}")
            elif prop.get("type") == "array":
                check(prop.get("items", {}), f"{label}.{name}[]")

    for tool in tools:
        schema = tool["api_schema"]
        for name, prop in (schema.get("path_params_schema") or {}).items():
            assert prop.get("description"), f"{tool['name']}.{name} has no description"
        if "query_params_schema" in schema:
            check(schema["query_params_schema"], f"{tool['name']}.query")
        if "request_body_schema" in schema:
            check(schema["request_body_schema"], f"{tool['name']}.body")


def test_write_tools_require_explicit_confirmation(tools):
    """update_order_line must not be callable without the confirmation flag."""
    tool = next(t for t in tools if t["name"] == "update_order_line")
    body = tool["api_schema"]["request_body_schema"]
    assert "customer_confirmed" in body["required"]
    assert "quantity" in body["required"]


def test_rfq_tool_requires_resolved_skus(tools):
    tool = next(t for t in tools if t["name"] == "create_rfq")
    body = tool["api_schema"]["request_body_schema"]
    assert set(body["required"]) == {"customer_account_number", "lines"}
    item = body["properties"]["lines"]["items"]
    assert set(item["required"]) == {"sku", "quantity"}


def test_session_state_is_captured_via_dynamic_variables(tools):
    """The PO and customer carry across turns without the model re-deriving them."""
    lookup = next(t for t in tools if t["name"] == "lookup_order")
    assigned = {a["dynamic_variable"]: a["value_path"] for a in lookup["assignments"]}
    assert assigned["active_po_number"] == "po_number"
    assert assigned["current_customer_account"] == "customer.account_number"

    rfq = next(t for t in tools if t["name"] == "create_rfq")
    assert rfq["assignments"][0]["dynamic_variable"] == "active_rfq_number"


def test_agent_config_is_valid_json_without_an_inline_prompt(tools):
    """The prompt lives in prompt.md; agent.json must not fork a second copy."""
    config = json.loads((AGENT_DIR / "agent.json").read_text())
    prompt_config = config["conversation_config"]["agent"]["prompt"]
    assert "prompt" not in prompt_config
    assert config["conversation_config"]["agent"]["first_message"]


def test_prompt_states_the_core_grounding_rule():
    prompt = (AGENT_DIR / "prompt.md").read_text().lower()
    assert "never state a business fact you have not retrieved" in prompt
    # Every tool must be named somewhere in the prompt.
    for name in EXPECTED_TOOLS:
        assert name in prompt, f"prompt never mentions {name}"
