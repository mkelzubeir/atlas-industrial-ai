"""Inventory availability.

Kept as its own tool rather than folded into product search on purpose. A
product existing in the catalog says nothing about whether Atlas can ship 600 of
them this week, and an agent that conflates the two will confidently overpromise.
Separating the endpoints makes the sequencing explicit and testable: resolve the
SKU, *then* ask about stock.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import ErrorCode, not_found
from app.models import Inventory, Product


def get_inventory(session: Session, sku: str, requested_quantity: int | None = None) -> dict:
    sku = (sku or "").strip().upper()
    product = session.get(Product, sku)
    if product is None:
        raise not_found(
            ErrorCode.PRODUCT_NOT_FOUND,
            f"There is no Atlas product with SKU {sku}.",
            sku=sku,
        )

    record: Inventory | None = product.inventory
    if record is None:  # pragma: no cover - every seeded product has inventory
        raise not_found(
            ErrorCode.PRODUCT_NOT_FOUND,
            f"No inventory record exists for SKU {sku}.",
            sku=sku,
        )

    available = record.quantity_available
    payload = {
        "sku": product.sku,
        "product_name": product.name,
        "unit_of_measure": product.unit_of_measure,
        "quantity_available": available,
        "quantity_on_hand": record.quantity_on_hand,
        "quantity_allocated": record.quantity_allocated,
        "warehouse": record.warehouse,
        "expected_restock_date": record.expected_restock_date,
        "requested_quantity": requested_quantity,
        "can_fulfil": None,
        "shortfall": None,
    }

    if requested_quantity is not None:
        payload["can_fulfil"] = available >= requested_quantity
        payload["shortfall"] = max(requested_quantity - available, 0)

    return payload
