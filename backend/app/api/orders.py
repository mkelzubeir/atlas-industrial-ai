"""Purchase-order endpoints, including the one guarded write."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Path
from sqlalchemy.orm import Session

from app.api.deps import fault_gate
from app.db import get_session
from app.logging_config import log_event
from app.schemas import (
    OrderResponse,
    ShipmentsResponse,
    UpdateOrderLineRequest,
    UpdateOrderLineResponse,
)
from app.services import orders

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get(
    "/{po_number}",
    response_model=OrderResponse,
    summary="Look up a purchase order with its lines, shipments and edit eligibility",
)
def get_order(
    po_number: str = Path(..., description='PO number. "PO 1847", "#1847" and "1847" all work.'),
    session: Session = Depends(get_session),
    _fault: None = Depends(fault_gate("orders")),
) -> OrderResponse:
    order = orders.get_order(session, po_number)
    payload = orders.serialise_order(order)
    log_event(
        "tool.lookup_order",
        po_number=payload["po_number"],
        status=payload["status"],
        line_count=payload["line_count"],
        order_modifiable=payload["order_modifiable"],
    )
    return OrderResponse.model_validate(payload)


@router.get(
    "/{po_number}/shipments",
    response_model=ShipmentsResponse,
    summary="Shipment and expected-date information for a purchase order",
)
def get_shipments(
    po_number: str = Path(..., description="PO number."),
    session: Session = Depends(get_session),
    _fault: None = Depends(fault_gate("shipments")),
) -> ShipmentsResponse:
    order = orders.get_order(session, po_number)
    payload = orders.serialise_shipments(order)
    log_event(
        "tool.lookup_shipment",
        po_number=payload["po_number"],
        shipment_count=payload["shipment_count"],
    )
    return ShipmentsResponse.model_validate(payload)


@router.patch(
    "/{po_number}/lines/{line_number}",
    response_model=UpdateOrderLineResponse,
    summary="Change the quantity on one order line (validated server-side)",
    responses={
        409: {"description": "The change is not permitted by Atlas order rules."},
        404: {"description": "No such order or line."},
    },
)
def update_line(
    payload: UpdateOrderLineRequest,
    po_number: str = Path(..., description="PO number."),
    line_number: int = Path(..., ge=1, description="Line number as shown by lookup_order."),
    session: Session = Depends(get_session),
    x_conversation_id: str | None = Header(default=None),
    _fault: None = Depends(fault_gate("orders")),
) -> UpdateOrderLineResponse:
    """Apply a quantity change.

    The request body asserts `customer_confirmed`. That is an attestation by the
    agent, not proof -- but it makes the confirmation step an explicit, audited
    part of the contract rather than something that only ever existed in the
    prompt. Every acceptance and every refusal is written to `audit_events`.
    """
    result = orders.update_line_quantity(
        session,
        po_number=po_number,
        line_number=line_number,
        new_quantity=payload.quantity,
        customer_confirmed=payload.customer_confirmed,
        expected_current_quantity=payload.expected_current_quantity,
        conversation_id=payload.conversation_id or x_conversation_id,
        reason=payload.reason,
    )
    log_event(
        "tool.update_order_line",
        po_number=result["po_number"],
        line_number=result["line_number"],
        previous_quantity=result["previous_quantity"],
        new_quantity=result["new_quantity"],
        audit_event_id=result["audit_event_id"],
    )
    return UpdateOrderLineResponse.model_validate(result)
