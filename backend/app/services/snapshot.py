"""Read-only snapshot of the synthetic environment, for the demo data browser.

Someone trying this demo has no way to guess that PO 1847 exists, or that
asking for "M8 stainless screws" is deliberately ambiguous. Without that, the
best they can do is ask vague questions and get vague answers.

This assembles the whole (small) synthetic world in one response so the UI can
show what there is to talk about. It is demo-only: a real distributor would
never expose every customer's order book on one endpoint, which is exactly why
it lives behind the demo gate rather than in the business API.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Customer,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Rfq,
    RfqLine,
    Shipment,
)
from app.rules import line_is_modifiable, order_is_modifiable


def build_snapshot(session: Session) -> dict:
    customers = list(session.scalars(select(Customer).order_by(Customer.company_name)))
    orders = list(
        session.scalars(
            select(PurchaseOrder)
            .options(
                selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.product),
                selectinload(PurchaseOrder.shipments).selectinload(Shipment.lines),
                selectinload(PurchaseOrder.customer),
            )
            .order_by(PurchaseOrder.po_number)
        )
    )
    products = list(
        session.scalars(
            select(Product).options(selectinload(Product.inventory)).order_by(Product.sku)
        )
    )
    rfqs = list(
        session.scalars(
            select(Rfq)
            .options(selectinload(Rfq.lines).selectinload(RfqLine.product), selectinload(Rfq.customer))
            .order_by(Rfq.rfq_number)
        )
    )

    orders_by_customer: dict[int, int] = {}
    for order in orders:
        orders_by_customer[order.customer_id] = orders_by_customer.get(order.customer_id, 0) + 1

    return {
        "customers": [
            {
                "account_number": c.account_number,
                "company_name": c.company_name,
                "contact_name": c.contact_name,
                "email": c.email,
                "phone": c.phone,
                "status": c.status.value,
                "order_count": orders_by_customer.get(c.id, 0),
            }
            for c in customers
        ],
        "orders": [
            {
                "po_number": o.po_number,
                "company_name": o.customer.company_name,
                "account_number": o.customer.account_number,
                "status": o.status.value,
                "modifiable": order_is_modifiable(o),
                "created_at": o.created_at.isoformat(),
                "customer_reference": o.customer_reference,
                "lines": [
                    {
                        "line_number": line.line_number,
                        "sku": line.sku,
                        "product_name": line.product.name,
                        "quantity": line.quantity,
                        "unit_of_measure": line.product.unit_of_measure,
                        "status": line.status.value,
                        "modifiable": line_is_modifiable(o, line),
                    }
                    for line in o.lines
                ],
                "shipments": [
                    {
                        "carrier": s.carrier,
                        "status": s.status.value,
                        "estimated_ship_date": (
                            s.estimated_ship_date.isoformat() if s.estimated_ship_date else None
                        ),
                        "estimated_ship_day": (
                            s.estimated_ship_date.strftime("%A") if s.estimated_ship_date else None
                        ),
                        "tracking_number": s.tracking_number,
                        "line_numbers": sorted(line.line_number for line in s.lines),
                    }
                    for s in o.shipments
                ],
            }
            for o in orders
        ],
        "products": [
            {
                "sku": p.sku,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "unit_of_measure": p.unit_of_measure,
                "unit_price": float(p.unit_price),
                "attributes": p.attributes or {},
                "quantity_available": p.inventory.quantity_available if p.inventory else 0,
                "quantity_on_hand": p.inventory.quantity_on_hand if p.inventory else 0,
                "expected_restock_date": (
                    p.inventory.expected_restock_date.isoformat()
                    if p.inventory and p.inventory.expected_restock_date
                    else None
                ),
            }
            for p in products
        ],
        "rfqs": [
            {
                "rfq_number": r.rfq_number,
                "company_name": r.customer.company_name,
                "status": r.status.value,
                "source": r.source,
                "created_at": r.created_at.isoformat(),
                "lines": [
                    {
                        "sku": line.sku,
                        "product_name": line.product.name,
                        "quantity": line.quantity,
                    }
                    for line in r.lines
                ],
            }
            for r in rfqs
        ],
        "counts": {
            "customers": len(customers),
            "orders": len(orders),
            "products": len(products),
            "rfqs": len(rfqs),
        },
    }
