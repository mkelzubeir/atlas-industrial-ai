"""Deterministic business rules for the synthetic Atlas environment.

This module is the point of the whole project.

The language model is told these rules in its system prompt, but being *told* a
rule is not the same as the rule being *true*. Everything here is a pure
function over database state, with no model in the loop. If the agent decides to
modify a shipped order anyway -- because it misheard, hallucinated, or a caller
talked it into doing so -- `check_line_modifiable` still returns a rejection and
the write never happens.

Keeping the rules as pure functions (rather than inline `if` statements in the
route handlers) means they can be unit-tested directly, and the same rule that
guards the write also powers the read-only "can I change this?" preview the
agent uses before asking the caller to confirm.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.errors import ErrorCode
from app.models import Inventory, LineStatus, OrderStatus, PurchaseOrder, PurchaseOrderLine

# --------------------------------------------------------------------------
# Rule constants. Named so the README, the prompt and the tests can all cite
# the same source of truth.
# --------------------------------------------------------------------------

#: Order states in which line quantities may still be edited at all.
MODIFIABLE_ORDER_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.DRAFT, OrderStatus.CONFIRMED, OrderStatus.PROCESSING}
)

#: Line states that are terminal -- no edit is possible regardless of the order.
TERMINAL_LINE_STATUSES: frozenset[LineStatus] = frozenset(
    {LineStatus.SHIPPED, LineStatus.CANCELLED}
)

#: Maximum quantity a single line may hold. Guards against a mis-transcribed
#: "two hundred" becoming 200000 with no ceiling.
MAX_LINE_QUANTITY = 100_000


@dataclass(frozen=True)
class RuleFailure:
    """A rejected change: a stable code plus a sentence the agent can speak."""

    code: str
    message: str
    details: dict | None = None


@dataclass(frozen=True)
class ModificationCheck:
    """Result of evaluating whether a line quantity change is permitted."""

    allowed: bool
    failure: RuleFailure | None = None
    #: True when the line is editable but only downward (stock already committed).
    decrease_only: bool = False

    @property
    def code(self) -> str | None:
        return self.failure.code if self.failure else None


def _order_state_failure(order: PurchaseOrder) -> RuleFailure | None:
    """Rule 1: the order as a whole must be in an editable state."""
    if order.status in MODIFIABLE_ORDER_STATUSES:
        return None

    if order.status is OrderStatus.SHIPPED:
        message = (
            f"Purchase order {order.po_number} has already shipped, so its lines can no longer "
            "be changed."
        )
    elif order.status is OrderStatus.CANCELLED:
        message = (
            f"Purchase order {order.po_number} was cancelled, so it can no longer be changed."
        )
    else:  # pragma: no cover - defensive; every status is covered above
        message = f"Purchase order {order.po_number} is not in a modifiable state."

    return RuleFailure(
        ErrorCode.ORDER_NOT_MODIFIABLE,
        message,
        {"po_number": order.po_number, "order_status": order.status.value},
    )


def _line_state_failure(order: PurchaseOrder, line: PurchaseOrderLine) -> RuleFailure | None:
    """Rule 2: the individual line must not have reached a terminal state.

    This is separate from rule 1 on purpose. A partially shipped order still
    sits in `processing`, so the order-level check passes while this specific
    line is already out the door.
    """
    if line.status not in TERMINAL_LINE_STATUSES:
        return None

    if line.status is LineStatus.SHIPPED:
        message = (
            f"Line {line.line_number} on purchase order {order.po_number} has already shipped, "
            "so its quantity can no longer be changed."
        )
    else:
        message = (
            f"Line {line.line_number} on purchase order {order.po_number} was cancelled, "
            "so its quantity can no longer be changed."
        )

    return RuleFailure(
        ErrorCode.LINE_NOT_MODIFIABLE,
        message,
        {
            "po_number": order.po_number,
            "line_number": line.line_number,
            "line_status": line.status.value,
        },
    )


def _quantity_failure(new_quantity: int) -> RuleFailure | None:
    """Rule 3: the requested quantity must be a sane positive integer.

    Note this rejects 0 rather than treating it as a cancellation. Deleting a
    line is a different business action with different rules, and silently
    turning "make it zero" into "cancel the line" is exactly the kind of
    inference an agent should not be allowed to make on a caller's behalf.
    """
    if new_quantity <= 0:
        return RuleFailure(
            ErrorCode.INVALID_QUANTITY,
            "The quantity must be at least 1. To remove an item from an order, the line has to "
            "be cancelled by an Atlas representative.",
            {"requested_quantity": new_quantity},
        )
    if new_quantity > MAX_LINE_QUANTITY:
        return RuleFailure(
            ErrorCode.INVALID_QUANTITY,
            f"The quantity {new_quantity:,} exceeds the maximum of {MAX_LINE_QUANTITY:,} units "
            "per line. An order that size needs to go through an Atlas account manager.",
            {"requested_quantity": new_quantity, "max_quantity": MAX_LINE_QUANTITY},
        )
    return None


def check_line_modifiable(
    order: PurchaseOrder,
    line: PurchaseOrderLine,
    new_quantity: int,
    inventory: Inventory | None = None,
) -> ModificationCheck:
    """Evaluate every rule governing a line-quantity change.

    Rules are evaluated in a fixed order, most fundamental first, so that the
    caller always hears the most relevant reason. Telling someone "we don't have
    enough stock" when the real problem is that their order shipped last week
    would be actively misleading.
    """
    for failure in (
        _order_state_failure(order),
        _line_state_failure(order, line),
        _quantity_failure(new_quantity),
    ):
        if failure is not None:
            return ModificationCheck(allowed=False, failure=failure)

    delta = new_quantity - line.quantity

    # Rule 4: once stock is committed to a line, the quantity may only come
    # down. Increasing it would need a fresh allocation against inventory that
    # has already been promised elsewhere.
    stock_committed = (
        order.status is OrderStatus.PROCESSING and line.status is LineStatus.ALLOCATED
    )
    if stock_committed and delta > 0:
        return ModificationCheck(
            allowed=False,
            decrease_only=True,
            failure=RuleFailure(
                ErrorCode.QUANTITY_INCREASE_NOT_ALLOWED,
                f"Line {line.line_number} on purchase order {order.po_number} is already "
                "allocated for picking, so the quantity can be reduced but not increased. "
                "Additional units would need to go on a new order.",
                {
                    "po_number": order.po_number,
                    "line_number": line.line_number,
                    "current_quantity": line.quantity,
                    "requested_quantity": new_quantity,
                },
            ),
        )

    # Rule 5: an increase must be covered by uncommitted stock. Only the *delta*
    # is checked -- the units already on the line are allocated to this customer.
    if delta > 0 and inventory is not None and delta > inventory.quantity_available:
        return ModificationCheck(
            allowed=False,
            failure=RuleFailure(
                ErrorCode.INSUFFICIENT_INVENTORY,
                f"Increasing line {line.line_number} by {delta} units is not possible right now. "
                f"Only {inventory.quantity_available} additional units of {line.sku} are "
                "available.",
                {
                    "sku": line.sku,
                    "additional_units_requested": delta,
                    "quantity_available": inventory.quantity_available,
                    "expected_restock_date": (
                        inventory.expected_restock_date.isoformat()
                        if inventory.expected_restock_date
                        else None
                    ),
                },
            ),
        )

    return ModificationCheck(allowed=True, decrease_only=stock_committed)


def order_is_modifiable(order: PurchaseOrder) -> bool:
    """Order-level convenience used to annotate read responses."""
    return _order_state_failure(order) is None


def line_is_modifiable(order: PurchaseOrder, line: PurchaseOrderLine) -> bool:
    """Line-level convenience used to annotate read responses.

    The agent reads this flag off a `lookup_order` result to decide whether it
    can promise a change before it attempts one -- which is what stops the
    conversation from confidently offering something the API will refuse.
    """
    return _order_state_failure(order) is None and _line_state_failure(order, line) is None
