"""Unit tests for the rules module itself.

These bypass HTTP entirely. The same functions that guard the write also
annotate the read responses, so testing them directly pins the behaviour
independently of any endpoint.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Inventory, PurchaseOrder
from app.rules import (
    MAX_LINE_QUANTITY,
    check_line_modifiable,
    line_is_modifiable,
    order_is_modifiable,
)


@pytest.fixture
def order_factory(session):
    def _get(po_number: str) -> PurchaseOrder:
        return session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))

    return _get


def test_processing_order_is_modifiable(order_factory):
    assert order_is_modifiable(order_factory("1847")) is True


def test_draft_and_confirmed_orders_are_modifiable(order_factory):
    assert order_is_modifiable(order_factory("2014")) is True
    assert order_is_modifiable(order_factory("1932")) is True


@pytest.mark.parametrize("po_number", ["1260", "2001"])
def test_terminal_orders_are_not_modifiable(order_factory, po_number):
    assert order_is_modifiable(order_factory(po_number)) is False


def test_shipped_line_is_not_modifiable_even_on_an_open_order(order_factory):
    order = order_factory("1905")
    assert order_is_modifiable(order) is True
    assert line_is_modifiable(order, order.lines[0]) is False
    assert line_is_modifiable(order, order.lines[2]) is True


def test_decrease_on_allocated_line_is_allowed(session, order_factory):
    order = order_factory("1847")
    line = order.lines[0]
    check = check_line_modifiable(order, line, 400, session.get(Inventory, line.sku))
    assert check.allowed is True
    assert check.decrease_only is True


def test_increase_on_allocated_line_is_refused(session, order_factory):
    order = order_factory("1847")
    line = order.lines[0]
    check = check_line_modifiable(order, line, 800, session.get(Inventory, line.sku))
    assert check.allowed is False
    assert check.code == "QUANTITY_INCREASE_NOT_ALLOWED"


def test_rules_are_evaluated_most_fundamental_first(session, order_factory):
    """A shipped order reports as shipped, not as 'quantity invalid'.

    Telling a caller the wrong reason is worse than telling them nothing, so
    ordering matters: even with a nonsense quantity, the shipped status wins.
    """
    order = order_factory("1260")
    line = order.lines[0]
    check = check_line_modifiable(order, line, -5, session.get(Inventory, line.sku))
    assert check.code == "ORDER_NOT_MODIFIABLE"


@pytest.mark.parametrize("quantity", [0, -1, MAX_LINE_QUANTITY + 1])
def test_out_of_range_quantities_are_refused(session, order_factory, quantity):
    order = order_factory("1847")
    line = order.lines[1]
    check = check_line_modifiable(order, line, quantity, session.get(Inventory, line.sku))
    assert check.allowed is False
    assert check.code == "INVALID_QUANTITY"


def test_increase_beyond_available_stock_is_refused(session, order_factory):
    order = order_factory("1905")
    line = order.lines[2]  # open line, shop towels
    inventory = session.get(Inventory, line.sku)
    check = check_line_modifiable(order, line, inventory.quantity_available + 1000, inventory)
    assert check.allowed is False
    assert check.code == "INSUFFICIENT_INVENTORY"


def test_only_the_delta_is_checked_against_stock(session, order_factory):
    """Units already on the line are the customer's; only the increase is new."""
    order = order_factory("1905")
    line = order.lines[2]
    inventory = session.get(Inventory, line.sku)
    exactly_available = line.quantity + inventory.quantity_available
    assert check_line_modifiable(order, line, exactly_available, inventory).allowed is True
    assert check_line_modifiable(order, line, exactly_available + 1, inventory).allowed is False


def test_failure_messages_are_written_to_be_spoken(session, order_factory):
    order = order_factory("1260")
    check = check_line_modifiable(order, order.lines[0], 10, None)
    message = check.failure.message
    assert message.endswith(".")
    assert "1260" in message
    # No codes, field names or JSON in something the caller will hear.
    assert "_" not in message and "{" not in message
