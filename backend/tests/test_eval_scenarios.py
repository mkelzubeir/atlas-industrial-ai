"""Validate the conversational evaluation suite against the real seed data.

The scenarios name concrete PO numbers, SKUs and quantities ("reduce the
washers on 1847 from 500 to 200"). If the seed data changes and a scenario is
not updated with it, the eval would fail for a reason that has nothing to do
with the agent -- and it would be easy to misread that as a model regression.

These tests keep the two in step, and run without touching the ElevenLabs API.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Product, PurchaseOrder

EVALS_PATH = Path(__file__).resolve().parents[2] / "evals" / "scenarios.json"

REQUIRED_IDS = {f"EVAL-{n:03d}" for n in range(1, 11)}
VALID_TYPES = {"tool", "simulation", "llm"}

# Every tool the scenarios are allowed to reference.
KNOWN_TOOLS = {
    "lookup_order",
    "lookup_shipment",
    "search_products",
    "check_inventory",
    "search_customer",
    "create_rfq",
    "update_order_line",
}


@pytest.fixture(scope="module")
def scenarios() -> list[dict]:
    return json.loads(EVALS_PATH.read_text())["scenarios"]


def test_the_ten_required_scenarios_are_present(scenarios):
    ids = {s["id"] for s in scenarios}
    assert REQUIRED_IDS <= ids, f"missing {sorted(REQUIRED_IDS - ids)}"


def test_scenario_ids_are_unique(scenarios):
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids))


def test_every_scenario_is_well_formed(scenarios):
    for scenario in scenarios:
        assert scenario["type"] in VALID_TYPES, scenario["id"]
        assert scenario["title"], scenario["id"]
        # Says what the case is actually for -- a scenario nobody can explain
        # is a scenario nobody will maintain.
        assert scenario["tests"], scenario["id"]

        if scenario["type"] == "simulation":
            assert scenario["simulation_scenario"], scenario["id"]
            assert len(scenario["success_conditions"]) >= 2, scenario["id"]
            assert scenario.get("max_turns", 0) > 0, scenario["id"]
        if scenario["type"] == "tool":
            assert scenario["chat_history"], scenario["id"]
            assert scenario["expect_tool"]["name"] in KNOWN_TOOLS, scenario["id"]


def test_grounding_scenarios_assert_a_negative(scenarios):
    """The cases that matter most check what the agent must NOT say.

    "Did it answer correctly?" is easy to pass by luck. "Did it avoid stating a
    number it never retrieved?" is the question that catches hallucination.
    """
    for sid in ("EVAL-002", "EVAL-003", "EVAL-010", "EVAL-011"):
        scenario = next(s for s in scenarios if s["id"] == sid)
        negatives = [c for c in scenario["success_conditions"] if " NOT " in c or "did not" in c]
        assert negatives, f"{sid} has no negative success condition"


def test_referenced_orders_exist_in_the_seed(session, scenarios):
    """Catches a scenario pointing at a PO that no longer exists."""
    po_numbers = {"1847", "1260", "9999"}
    seeded = {po for (po,) in session.execute(select(PurchaseOrder.po_number))}
    for po in po_numbers - {"9999"}:  # 9999 is meant to be absent
        assert po in seeded, f"scenarios reference PO {po}, which is not seeded"
    assert "9999" not in seeded, "EVAL-002 requires PO 9999 to NOT exist"


def test_referenced_skus_exist_in_the_seed(session, scenarios):
    raw = EVALS_PATH.read_text()
    referenced = {token for token in ("ATL-1030", "ATL-2110") if token in raw}
    seeded = {sku for (sku,) in session.execute(select(Product.sku))}
    for sku in referenced:
        assert sku in seeded, f"scenarios reference SKU {sku}, which is not seeded"


def test_flagship_scenario_matches_the_seeded_quantities(session, scenarios):
    """EVAL-005 and EVAL-007 say 'from 500 to 200'. Check the 500 is real."""
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "1847"))
    washers = next(line for line in order.lines if line.sku == "ATL-1310")
    assert washers.quantity == 500, "EVAL-005/007 assume the washer line starts at 500"
    assert washers.line_number == 2, "EVAL-005/007 assume the washer line is line 2"

    bolts = order.lines[0]
    assert bolts.quantity == 600, "EVAL-007 assumes 600 bolts"
    assert bolts.sku == "ATL-1030"


def test_shipped_order_scenario_matches_the_seed(session):
    """EVAL-006 needs PO 1260 to actually be shipped."""
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "1260"))
    assert order.status.value == "shipped"
    assert order.lines[0].quantity == 40, "EVAL-006 assumes the bearing line is 40"


def test_allocated_line_scenario_matches_the_seed(session):
    """EVAL-012 needs an allocated line on a processing order."""
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "1847"))
    assert order.status.value == "processing"
    assert order.lines[0].status.value == "allocated"


def test_mocked_tools_are_real_tools(scenarios):
    for scenario in scenarios:
        for tool_name in (scenario.get("mock_tools") or {}):
            assert tool_name in KNOWN_TOOLS, f"{scenario['id']} mocks unknown tool {tool_name}"


def test_every_write_scenario_declares_its_expected_final_state(scenarios):
    """A conversational pass is not enough for a scenario that changes state."""
    for scenario in scenarios:
        assert scenario.get("expected_final_state"), scenario["id"]
