"""Purchase-order lookup, serialisation, and the guarded line-quantity write.

The serialisation here does real work. Rather than handing the model raw rows,
each line is annotated with `modifiable` and a plain-English `modification_note`
computed from `app.rules`. The agent therefore knows what it may offer *before*
it offers it, which is what prevents the conversational failure of promising a
change the API then refuses.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import AtlasError, ErrorCode, not_found
from app.models import (
    Inventory,
    LineStatus,
    OrderStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
)
from app.rules import check_line_modifiable, line_is_modifiable, order_is_modifiable
from app.services import audit


def _normalise_po_number(po_number: str) -> str:
    """Accept the many ways a caller says a PO number.

    "PO 1847", "po-1847", "#1847" and "1847" are all the same order. Speech
    recognition will not normalise this and neither will the model reliably, so
    the API does it once, here.
    """
    cleaned = (po_number or "").strip().upper()
    for prefix in ("PURCHASE ORDER", "ORDER", "PO"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned.lstrip("#-: ").strip()


def get_order(session: Session, po_number: str) -> PurchaseOrder:
    normalised = _normalise_po_number(po_number)
    statement = (
        select(PurchaseOrder)
        .where(PurchaseOrder.po_number == normalised)
        .options(
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.product),
            selectinload(PurchaseOrder.shipments).selectinload(Shipment.lines),
            selectinload(PurchaseOrder.customer),
        )
    )
    order = session.scalar(statement)
    if order is None:
        raise not_found(
            ErrorCode.ORDER_NOT_FOUND,
            f"I could not find purchase order {normalised} in the Atlas system.",
            po_number=normalised,
        )
    return order


def serialise_shipment(shipment: Shipment) -> dict:
    def day_name(value) -> str | None:
        return value.strftime("%A") if value else None

    return {
        "shipment_id": shipment.id,
        "carrier": shipment.carrier,
        "status": shipment.status.value,
        "estimated_ship_date": shipment.estimated_ship_date,
        "estimated_ship_day": day_name(shipment.estimated_ship_date),
        "estimated_delivery_date": shipment.estimated_delivery_date,
        "estimated_delivery_day": day_name(shipment.estimated_delivery_date),
        "tracking_number": shipment.tracking_number,
        "line_numbers": sorted(line.line_number for line in shipment.lines),
    }


def _modification_note(order: PurchaseOrder, line: PurchaseOrderLine) -> str | None:
    """A sentence explaining this line's editability, ready to be spoken."""
    if not order_is_modifiable(order):
        if order.status is OrderStatus.SHIPPED:
            return "The order has already shipped, so nothing on it can be changed."
        if order.status is OrderStatus.CANCELLED:
            return "The order was cancelled, so nothing on it can be changed."
        return "The order is not in a modifiable state."

    if line.status is LineStatus.SHIPPED:
        return "This line has already shipped, so its quantity can no longer be changed."
    if line.status is LineStatus.CANCELLED:
        return "This line was cancelled, so its quantity can no longer be changed."
    if order.status is OrderStatus.PROCESSING and line.status is LineStatus.ALLOCATED:
        return (
            "This line is already allocated for picking, so the quantity can be reduced "
            "but not increased."
        )
    return None


def serialise_order(order: PurchaseOrder) -> dict:
    shipments_by_id = {s.id: serialise_shipment(s) for s in order.shipments}

    lines = []
    for line in order.lines:
        lines.append(
            {
                "line_number": line.line_number,
                "sku": line.sku,
                "product_name": line.product.name,
                "quantity": line.quantity,
                "unit_of_measure": line.product.unit_of_measure,
                "unit_price": float(line.unit_price),
                "status": line.status.value,
                "modifiable": line_is_modifiable(order, line),
                "modification_note": _modification_note(order, line),
                "shipment": shipments_by_id.get(line.shipment_id),
            }
        )

    return {
        "po_number": order.po_number,
        "status": order.status.value,
        "order_modifiable": order_is_modifiable(order),
        "customer": order.customer,
        "customer_reference": order.customer_reference,
        "created_at": order.created_at,
        "line_count": len(lines),
        "lines": lines,
        "shipments": [shipments_by_id[s.id] for s in order.shipments],
    }


def serialise_shipments(order: PurchaseOrder) -> dict:
    return {
        "po_number": order.po_number,
        "order_status": order.status.value,
        "shipment_count": len(order.shipments),
        "shipments": [serialise_shipment(s) for s in order.shipments],
    }


def _find_line(order: PurchaseOrder, line_number: int) -> PurchaseOrderLine:
    for line in order.lines:
        if line.line_number == line_number:
            return line
    raise not_found(
        ErrorCode.LINE_NOT_FOUND,
        f"Purchase order {order.po_number} has no line {line_number}. "
        f"It has {len(order.lines)} line(s).",
        po_number=order.po_number,
        line_number=line_number,
        available_line_numbers=[line.line_number for line in order.lines],
    )


def update_line_quantity(
    session: Session,
    *,
    po_number: str,
    line_number: int,
    new_quantity: int,
    customer_confirmed: bool,
    expected_current_quantity: int | None = None,
    conversation_id: str | None = None,
    reason: str | None = None,
) -> dict:
    """Apply a line-quantity change, or refuse it and say why.

    Every refusal path writes an audit event before raising. That is what lets
    the evaluation suite assert not merely "the quantity did not change" but
    "the system recorded that it declined, and for which reason".
    """
    order = get_order(session, po_number)
    line = _find_line(order, line_number)
    previous_quantity = line.quantity

    def reject(code: str, message: str, details: dict | None = None) -> AtlasError:
        audit.record(
            session,
            event_type="order_line_quantity_change_rejected",
            entity_type="purchase_order_line",
            entity_id=f"{order.po_number}:{line.line_number}",
            outcome="rejected",
            conversation_id=conversation_id,
            payload={
                "po_number": order.po_number,
                "line_number": line.line_number,
                "sku": line.sku,
                "current_quantity": previous_quantity,
                "requested_quantity": new_quantity,
                "rejection_code": code,
                "order_status": order.status.value,
                "line_status": line.status.value,
                "customer_confirmed": customer_confirmed,
            },
        )
        session.commit()
        http_status = 409 if code != ErrorCode.INVALID_QUANTITY else 400
        return AtlasError(code, message, http_status=http_status, details=details or {})

    # Optimistic concurrency. If the agent read the order, held a conversation,
    # and something changed underneath it, overwriting blindly would discard the
    # other change. Refusing lets the agent re-read and re-confirm.
    if expected_current_quantity is not None and expected_current_quantity != previous_quantity:
        raise reject(
            ErrorCode.LINE_NOT_MODIFIABLE,
            f"Line {line_number} on purchase order {order.po_number} now shows "
            f"{previous_quantity} units, not {expected_current_quantity}. "
            "The order changed since it was last checked, so nothing was updated.",
            {
                "po_number": order.po_number,
                "line_number": line_number,
                "current_quantity": previous_quantity,
                "expected_current_quantity": expected_current_quantity,
            },
        )

    inventory = session.get(Inventory, line.sku)
    check = check_line_modifiable(order, line, new_quantity, inventory)
    if not check.allowed:
        failure = check.failure
        assert failure is not None  # guaranteed when allowed is False
        raise reject(failure.code, failure.message, failure.details)

    # A no-op is worth reporting honestly rather than claiming a change.
    if new_quantity == previous_quantity:
        event = audit.record(
            session,
            event_type="order_line_quantity_change_noop",
            entity_type="purchase_order_line",
            entity_id=f"{order.po_number}:{line.line_number}",
            outcome="success",
            conversation_id=conversation_id,
            payload={
                "po_number": order.po_number,
                "line_number": line.line_number,
                "sku": line.sku,
                "quantity": previous_quantity,
            },
        )
        session.commit()
        return {
            "po_number": order.po_number,
            "line_number": line.line_number,
            "sku": line.sku,
            "product_name": line.product.name,
            "previous_quantity": previous_quantity,
            "new_quantity": previous_quantity,
            "line_status": line.status.value,
            "order_status": order.status.value,
            "audit_event_id": event.id,
            "message": (
                f"Line {line.line_number} on purchase order {order.po_number} was already set to "
                f"{previous_quantity}, so nothing changed."
            ),
        }

    delta = new_quantity - previous_quantity
    line.quantity = new_quantity

    # Keep the allocation ledger honest: an allocated line holds committed
    # stock, so changing its quantity moves the same amount in inventory.
    if line.status is LineStatus.ALLOCATED and inventory is not None:
        inventory.quantity_allocated = max(inventory.quantity_allocated + delta, 0)

    event = audit.record(
        session,
        event_type="order_line_quantity_changed",
        entity_type="purchase_order_line",
        entity_id=f"{order.po_number}:{line.line_number}",
        outcome="success",
        conversation_id=conversation_id,
        payload={
            "po_number": order.po_number,
            "line_number": line.line_number,
            "sku": line.sku,
            "previous_quantity": previous_quantity,
            "new_quantity": new_quantity,
            "delta": delta,
            "order_status": order.status.value,
            "line_status": line.status.value,
            "customer_confirmed": customer_confirmed,
            "reason": reason,
        },
    )
    session.commit()

    direction = "reduced" if delta < 0 else "increased"
    return {
        "po_number": order.po_number,
        "line_number": line.line_number,
        "sku": line.sku,
        "product_name": line.product.name,
        "previous_quantity": previous_quantity,
        "new_quantity": new_quantity,
        "line_status": line.status.value,
        "order_status": order.status.value,
        "audit_event_id": event.id,
        "message": (
            f"Line {line.line_number} on purchase order {order.po_number} "
            f"({line.product.name}) is now {direction} from {previous_quantity} to "
            f"{new_quantity} {line.product.unit_of_measure}."
        ),
    }
