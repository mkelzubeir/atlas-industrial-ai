"""Builds the synthetic Atlas database from `seed.catalog`.

`reset_database()` is the single entry point, used by three callers:
the CLI (`python -m seed.seed`), the pytest fixtures, and the demo-only
`POST /api/demo/reset` endpoint. Having exactly one implementation is what
makes "reset before recording" trustworthy -- the demo cannot drift from what
the tests run against.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    AuditEvent,
    Customer,
    CustomerStatus,
    Inventory,
    LineStatus,
    OrderStatus,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Rfq,
    RfqLine,
    RfqStatus,
    Shipment,
    ShipmentStatus,
)
from seed import catalog


def _today() -> date:
    """Today in UTC. Explicit tz keeps the seeded dates reproducible."""
    return datetime.now(UTC).date()


def _next_weekday(reference: date, weekday: int) -> date:
    """The next occurrence of `weekday` strictly after `reference`.

    Monday is 0. Used so the flagship order always has a shipment landing on
    the upcoming Friday, however long ago the repository was written.
    """
    days_ahead = (weekday - reference.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return reference + timedelta(days=days_ahead)


def _seed_products(session: Session) -> None:
    for entry in catalog.PRODUCTS:
        session.add(Product(**entry))

    for sku, (on_hand, allocated, restock_in_days) in catalog.INVENTORY.items():
        session.add(
            Inventory(
                sku=sku,
                quantity_on_hand=on_hand,
                quantity_allocated=allocated,
                expected_restock_date=(
                    _today() + timedelta(days=restock_in_days) if restock_in_days else None
                ),
            )
        )


def _seed_customers(session: Session) -> dict[str, Customer]:
    by_account: dict[str, Customer] = {}
    for entry in catalog.CUSTOMERS:
        customer = Customer(
            account_number=entry["account_number"],
            company_name=entry["company_name"],
            contact_name=entry["contact_name"],
            email=entry["email"],
            phone=entry["phone"],
            status=CustomerStatus(entry["status"]),
        )
        session.add(customer)
        by_account[entry["account_number"]] = customer
    session.flush()
    return by_account


def _seed_orders(session: Session, customers: dict[str, Customer], prices: dict[str, float]) -> None:
    today = _today()
    now = datetime.now(UTC)

    for entry in catalog.ORDERS:
        order = PurchaseOrder(
            po_number=entry["po_number"],
            customer_id=customers[entry["account_number"]].id,
            status=OrderStatus(entry["status"]),
            customer_reference=entry.get("customer_reference"),
            created_at=now - timedelta(days=entry["created_days_ago"]),
        )
        session.add(order)
        session.flush()

        # Shipments first: lines carry a foreign key to them.
        shipments_by_ref: dict[str, Shipment] = {}
        for spec in entry.get("shipments", []):
            if "ship_on_next_weekday" in spec:
                ship_date = _next_weekday(today, spec["ship_on_next_weekday"])
            else:
                ship_date = today + timedelta(days=spec["ship_offset_days"])

            shipment = Shipment(
                purchase_order_id=order.id,
                carrier=spec["carrier"],
                status=ShipmentStatus(spec["status"]),
                estimated_ship_date=ship_date,
                estimated_delivery_date=ship_date + timedelta(days=spec["delivery_offset_days"]),
                tracking_number=spec.get("tracking_number"),
            )
            session.add(shipment)
            session.flush()
            shipments_by_ref[spec["ref"]] = shipment

        for index, line_spec in enumerate(entry["lines"], start=1):
            shipment_ref = line_spec.get("shipment")
            session.add(
                PurchaseOrderLine(
                    purchase_order_id=order.id,
                    line_number=index,
                    sku=line_spec["sku"],
                    quantity=line_spec["quantity"],
                    unit_price=prices[line_spec["sku"]],
                    status=LineStatus(line_spec["status"]),
                    shipment_id=(
                        shipments_by_ref[shipment_ref].id if shipment_ref else None
                    ),
                )
            )


def _seed_rfqs(session: Session, customers: dict[str, Customer]) -> None:
    now = datetime.now(UTC)
    for entry in catalog.RFQS:
        rfq = Rfq(
            rfq_number=entry["rfq_number"],
            customer_id=customers[entry["account_number"]].id,
            status=RfqStatus(entry["status"]),
            source=entry["source"],
            created_at=now - timedelta(days=entry["created_days_ago"]),
        )
        session.add(rfq)
        session.flush()
        for index, line in enumerate(entry["lines"], start=1):
            session.add(
                RfqLine(
                    rfq_id=rfq.id,
                    line_number=index,
                    sku=line["sku"],
                    quantity=line["quantity"],
                )
            )


def reset_database(session: Session | None = None) -> dict[str, int]:
    """Drop every table, recreate the schema, and reload the seed data.

    Returns a small summary so the demo-reset endpoint can report what it
    restored rather than a bare 204.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        # Close out any in-flight transaction before DDL: SQLite will not drop
        # tables that the current connection still holds open.
        session.rollback()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        prices = {p["sku"]: p["unit_price"] for p in catalog.PRODUCTS}

        _seed_products(session)
        customers = _seed_customers(session)
        _seed_orders(session, customers, prices)
        _seed_rfqs(session, customers)
        session.commit()

        return {
            "products": len(catalog.PRODUCTS),
            "customers": len(catalog.CUSTOMERS),
            "purchase_orders": len(catalog.ORDERS),
            "rfqs": len(catalog.RFQS),
            "audit_events": session.query(AuditEvent).count(),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def main() -> None:
    summary = reset_database()
    print("Atlas synthetic database seeded:")
    for key, value in summary.items():
        print(f"  {key:>16}: {value}")


if __name__ == "__main__":
    main()
