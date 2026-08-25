"""Inventory availability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import fault_gate
from app.db import get_session
from app.logging_config import log_event
from app.schemas import InventoryResponse
from app.services import inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get(
    "/{sku}",
    response_model=InventoryResponse,
    summary="Check available stock for one SKU",
)
def get(
    sku: str = Path(..., description="An exact Atlas SKU, e.g. ATL-1030."),
    requested_quantity: int | None = Query(
        None, ge=1, description="If given, the response answers whether this quantity can be met."
    ),
    session: Session = Depends(get_session),
    _fault: None = Depends(fault_gate("inventory")),
) -> InventoryResponse:
    result = inventory.get_inventory(session, sku, requested_quantity)
    log_event(
        "tool.check_inventory",
        sku=result["sku"],
        quantity_available=result["quantity_available"],
        requested_quantity=requested_quantity,
        can_fulfil=result["can_fulfil"],
    )
    return InventoryResponse.model_validate(result)
