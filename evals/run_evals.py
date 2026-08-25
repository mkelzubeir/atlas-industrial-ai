#!/usr/bin/env python3
"""Run the Atlas conversational evaluation suite.

Two layers of testing sit behind this project, and they answer different
questions:

* `backend/tests` (pytest) proves the **deterministic** half. Given this
  request, does the API return the right answer and refuse the right writes?
  No model is involved, so those tests are fast and never flake.

* This suite proves the half that depends on **model judgement**. Does the
  agent pick the right tool, build the right arguments, ask before guessing,
  confirm before writing, and admit when a tool fails?

The scenarios live in `evals/scenarios.json` and are executed through the
ElevenLabs agent-testing API, which drives a simulated caller against the real
agent and grades the transcript against the success conditions.

Two properties make the results trustworthy:

1. **The database is reset before the run.** Otherwise EVAL-005 passes once and
   fails on every re-run, because the washers are already at 200.
2. **State-changing scenarios are checked against the database afterwards**, not
   only against the transcript. An agent that *says* it reduced the line and did
   not is a failure this suite catches.

Usage
-----
    export ELEVENLABS_API_KEY=...
    export ATLAS_BASE_URL=http://127.0.0.1:8000      # local backend, for checks
    export ATLAS_API_KEY=...                         # if the backend requires it

    python evals/run_evals.py --dry-run    # validate the scenarios offline
    python evals/run_evals.py              # create/update the tests and run them
    python evals/run_evals.py --only EVAL-005 EVAL-007
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from el_client import ElevenLabsClient, Out, ProvisioningError  # noqa: E402

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"
AGENT_ID_FILE = REPO_ROOT / "agent" / ".agent-id"
TEST_NAME_PREFIX = "Atlas "

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 900


# ---------------------------------------------------------------------------
# The Atlas backend (for reset and post-run state checks)
# ---------------------------------------------------------------------------

class AtlasBackend:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _request(self, method: str, path: str) -> Any:
        request = urllib.request.Request(f"{self.base_url}{path}", method=method)
        request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("X-Atlas-Api-Key", self.api_key)
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode()
            return json.loads(payload) if payload else {}

    def reachable(self) -> bool:
        try:
            self._request("GET", "/health")
            return True
        except Exception:
            return False

    def reset(self) -> dict:
        return self._request("POST", "/api/demo/reset")

    def order(self, po_number: str) -> dict:
        return self._request("GET", f"/api/orders/{po_number}")

    def audit(self) -> list[dict]:
        return self._request("GET", "/api/demo/audit?limit=50").get("events", [])

    def line_quantity(self, po_number: str, line_number: int) -> int | None:
        try:
            order = self.order(po_number)
        except Exception:
            return None
        for line in order["lines"]:
            if line["line_number"] == line_number:
                return line["quantity"]
        return None


# ---------------------------------------------------------------------------
# Scenario -> ElevenLabs test payload
# ---------------------------------------------------------------------------

def build_test_body(scenario: dict, tool_ids: dict[str, str]) -> dict:
    """Translate one scenario into an agent-testing request body."""
    name = f"{TEST_NAME_PREFIX}{scenario['id']} — {scenario['title']}"

    if scenario["type"] == "tool":
        expected = scenario["expect_tool"]
        tool_id = tool_ids.get(expected["name"])
        if not tool_id:
            raise ProvisioningError(
                f"{scenario['id']} references tool {expected['name']!r}, which does not exist "
                "in the workspace. Run scripts/provision_agent.py first."
            )
        return {
            "type": "tool",
            "name": name,
            "chat_history": scenario["chat_history"],
            "tool_call_parameters": {
                "referenced_tool": {"id": tool_id, "type": "webhook"},
                "parameters": expected.get("parameters", []),
                "verify_absence": expected.get("verify_absence", False),
            },
        }

    if scenario["type"] == "simulation":
        body: dict[str, Any] = {
            "type": "simulation",
            "name": name,
            "simulation_scenario": scenario["simulation_scenario"],
            "success_conditions": scenario["success_conditions"],
            "simulation_max_turns": scenario.get("max_turns", 10),
        }
        # EVAL-010 forces a tool to fail so the agent's error handling is
        # observable. Everything else hits the real backend.
        mocks = scenario.get("mock_tools")
        if mocks:
            body["tool_mock_config"] = {
                "mocking_strategy": "selected",
                "mocked_tool_ids": [
                    tool_ids[name_] for name_ in mocks if name_ in tool_ids
                ],
                "fallback_strategy": "call_real_tool",
            }
            body["tool_mock_overrides"] = {
                name_: [
                    {
                        "mock_result": spec["mock_result"],
                        "is_error": spec.get("is_error", False),
                        "parameter_conditions": [],
                    }
                ]
                for name_, spec in mocks.items()
            }
        return body

    if scenario["type"] == "llm":
        return {
            "type": "llm",
            "name": name,
            "chat_history": scenario["chat_history"],
            "success_condition": scenario["success_condition"],
            "success_examples": scenario.get("success_examples", []),
            "failure_examples": scenario.get("failure_examples", []),
        }

    raise ProvisioningError(f"{scenario['id']} has unknown type {scenario['type']!r}")


# ---------------------------------------------------------------------------
# Post-run database assertions
# ---------------------------------------------------------------------------

def check_final_state(scenario: dict, backend: AtlasBackend) -> tuple[bool, str]:
    """Verify the database matches what the scenario expected.

    The transcript grader only reads what the agent *said*. These checks read
    what actually happened, which is the difference between an agent that made
    the change and one that claimed to.
    """
    sid = scenario["id"]

    if sid in {"EVAL-005", "EVAL-007"}:
        quantity = backend.line_quantity("1847", 2)
        if quantity != 200:
            return False, f"PO 1847 line 2 should be 200, found {quantity}"
        writes = [
            e
            for e in backend.audit()
            if e["event_type"] == "order_line_quantity_changed" and e["outcome"] == "success"
        ]
        if not writes:
            return False, "no successful order_line_quantity_changed audit event"
        return True, "line 2 = 200, write audited"

    if sid == "EVAL-006":
        quantity = backend.line_quantity("1260", 1)
        if quantity != 40:
            return False, f"PO 1260 line 1 must stay 40, found {quantity}"
        return True, "shipped order untouched"

    if sid == "EVAL-012":
        quantity = backend.line_quantity("1847", 1)
        if quantity != 600:
            return False, f"PO 1847 line 1 must stay 600, found {quantity}"
        return True, "allocated line untouched"

    if sid == "EVAL-011":
        quantity = backend.line_quantity("1847", 2)
        if quantity != 500:
            return False, f"PO 1847 line 2 must stay 500, found {quantity}"
        if backend.audit():
            return False, "a read-only conversation produced audit events"
        return True, "order unchanged, no writes"

    if sid in {"EVAL-008", "EVAL-009"}:
        created = [e for e in backend.audit() if e["event_type"] == "rfq_created"]
        if not created:
            return False, "no rfq_created audit event"
        lines = created[-1]["payload"].get("lines", [])
        skus = {line["sku"] for line in lines}
        if not {"ATL-1030", "ATL-2110"} <= skus:
            return False, f"RFQ lines were {sorted(skus)}, expected ATL-1030 and ATL-2110"
        return True, f"RFQ created with {len(lines)} lines"

    if scenario.get("expected_final_state") == "unchanged":
        if backend.audit():
            return False, "a read-only scenario produced audit events"
        return True, "no state changed"

    return True, "no database assertion for this scenario"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Atlas conversational eval suite.")
    parser.add_argument("--api-key", default=os.environ.get("ELEVENLABS_API_KEY", ""))
    parser.add_argument("--agent-id", default=os.environ.get("ATLAS_AGENT_ID", ""))
    parser.add_argument(
        "--atlas-base-url", default=os.environ.get("ATLAS_BASE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--atlas-api-key", default=os.environ.get("ATLAS_API_KEY", ""))
    parser.add_argument("--only", nargs="*", default=None, help="Run only these scenario ids.")
    parser.add_argument("--no-reset", action="store_true", help="Skip the demo-data reset.")
    parser.add_argument("--dry-run", action="store_true", help="Validate scenarios, call nothing.")
    args = parser.parse_args()

    try:
        scenarios = json.loads(SCENARIOS_PATH.read_text())["scenarios"]
        if args.only:
            wanted = set(args.only)
            scenarios = [s for s in scenarios if s["id"] in wanted]
            if not scenarios:
                raise ProvisioningError(f"No scenarios matched {sorted(wanted)}.")

        agent_id = args.agent_id or (
            AGENT_ID_FILE.read_text().strip() if AGENT_ID_FILE.exists() else ""
        )
        if not agent_id and not args.dry_run:
            raise ProvisioningError(
                "No agent id. Run scripts/provision_agent.py, or pass --agent-id."
            )
        if not args.api_key and not args.dry_run:
            raise ProvisioningError("ELEVENLABS_API_KEY is not set.")

        print()
        Out.step(f"Atlas evaluation suite — {len(scenarios)} scenario(s)")
        Out.same(f"agent    : {agent_id or '(dry run)'}")
        Out.same(f"backend  : {args.atlas_base_url}")
        if args.dry_run:
            Out.warn("dry run — scenarios are validated but nothing is executed")
        print()

        client = ElevenLabsClient(args.api_key or "dry-run", dry_run=args.dry_run)
        backend = AtlasBackend(args.atlas_base_url, args.atlas_api_key)

        # --- reset -------------------------------------------------------
        backend_up = backend.reachable()
        if args.dry_run:
            # A dry run validates request bodies. It must not mutate anything.
            Out.same("skipping demo reset (dry run)")
        elif not backend_up:
            Out.warn(
                f"Atlas backend not reachable at {args.atlas_base_url}. "
                "Database assertions will be skipped."
            )
        elif args.no_reset:
            Out.warn("skipping demo reset (--no-reset); write scenarios may not be repeatable")
        else:
            Out.step("Resetting demo data")
            restored = backend.reset()["restored"]
            Out.ok(f"restored {restored['purchase_orders']} orders, {restored['products']} products")

        # --- reconcile the tests -----------------------------------------
        Out.step("Reconciling test definitions")
        tool_ids = {}
        for tool in client.list_tools():
            name = (tool.get("tool_config") or {}).get("name") or tool.get("name")
            if name:
                tool_ids[name] = tool.get("id") or tool.get("tool_id")

        if args.dry_run and not tool_ids:
            # Offline: stand in placeholder ids so every scenario body can still
            # be built and validated.
            tool_names = [
                tool["name"]
                for tool in json.loads((REPO_ROOT / "agent" / "tools.json").read_text())
            ]
            tool_ids = {name: f"<dry-run-{name}>" for name in tool_names}
            Out.same(f"using placeholder ids for {len(tool_ids)} tools")

        existing = {t.get("name"): t.get("id") for t in client.list_tests()}

        test_ids: dict[str, str] = {}
        for scenario in scenarios:
            body = build_test_body(scenario, tool_ids)
            name = body["name"]
            if name in existing:
                client.update_test(existing[name], body)
                test_ids[scenario["id"]] = existing[name]
                Out.ok(f"{scenario['id']} updated")
            else:
                created = client.create_test(body)
                test_ids[scenario["id"]] = created.get("id") or created.get("test_id")
                Out.ok(f"{scenario['id']} created")

        if args.dry_run:
            print()
            Out.step("Dry run complete — every scenario built a valid request body")
            print()
            return 0

        # --- run ----------------------------------------------------------
        Out.step("Running tests")
        invocation = client.run_tests(agent_id, list(test_ids.values()))
        invocation_id = invocation.get("id") or invocation.get("test_invocation_id")
        Out.same(f"invocation {invocation_id}")

        deadline = time.time() + POLL_TIMEOUT_SECONDS
        runs: list[dict] = []
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            state = client.get_invocation(invocation_id)
            runs = state.get("test_runs", [])
            pending = [r for r in runs if r.get("status") == "pending"]
            Out.same(f"{len(runs) - len(pending)}/{len(runs)} complete")
            if runs and not pending:
                break
        else:
            Out.warn("timed out waiting for the invocation to finish")

        # --- report -------------------------------------------------------
        by_test_id = {r.get("test_id"): r for r in runs}
        print()
        Out.step("Results")

        failures = 0
        for scenario in scenarios:
            run = by_test_id.get(test_ids[scenario["id"]], {})
            status = run.get("status", "unknown")
            transcript_passed = status == "passed"

            state_passed, state_note = (True, "backend unreachable — skipped")
            if backend_up:
                state_passed, state_note = check_final_state(scenario, backend)

            passed = transcript_passed and state_passed
            label = f"{scenario['id']}  {scenario['title']}"
            if passed:
                Out.ok(label)
            else:
                failures += 1
                Out.fail(label)
                rationale = (run.get("condition_result") or {}).get("rationale")
                if not transcript_passed:
                    Out.same(f"    transcript: {status}" + (f" — {rationale}" if rationale else ""))
                if not state_passed:
                    Out.same(f"    database:   {state_note}")

        print()
        total = len(scenarios)
        if failures:
            Out.fail(f"{total - failures}/{total} passed, {failures} failed")
        else:
            Out.ok(f"{total}/{total} passed")
        print()
        return 1 if failures else 0

    except ProvisioningError as exc:
        print()
        Out.fail(str(exc))
        print()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
