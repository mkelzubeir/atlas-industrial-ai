"""SQLAlchemy ORM models for the synthetic Atlas business systems.

All data in these tables is fictional. Atlas Industrial Supply is not a real
company and none of these records describe a real customer, order or product.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrderStatus(str, enum.Enum):
    """Lifecycle of a purchase order.

    The ordering here is meaningful: an order moves forward through these states
    and the modification rules in `app.rules` key off them.
    """

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class LineStatus(str, enum.Enum):
    """Lifecycle of a single order line.

    A line can reach a terminal state ahead of its order: a partially shipped
    order still sits in `processing` while one of its lines is already `shipped`.
    """

    OPEN = "open"
    ALLOCATED = "allocated"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class ShipmentStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class RfqStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    PRICING = "pricing"
    QUOTED = "quoted"
    EXPIRED = "expired"


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(120), index=True)
    contact_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(40))
    status: Mapped[CustomerStatus] = mapped_column(
        Enum(CustomerStatus, native_enum=False), default=CustomerStatus.ACTIVE
    )

    orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="customer")
    rfqs: Mapped[list[Rfq]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(String(400))
    category: Mapped[str] = mapped_column(String(60), index=True)
    unit_of_measure: Mapped[str] = mapped_column(String(24), default="each")
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))
    # Distinguishing attributes (thread size, length, material, head style...).
    # Held as JSON because the meaningful attributes differ per category, and the
    # agent uses them verbatim when asking the caller a clarifying question.
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    # Space-separated extra terms callers actually say out loud ("cap screw",
    # "allen bolt"). Searched alongside name/description.
    search_terms: Mapped[str] = mapped_column(String(400), default="")

    inventory: Mapped[Inventory] = relationship(back_populates="product", uselist=False)


class Inventory(Base):
    __tablename__ = "inventory"

    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), primary_key=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0)
    expected_restock_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warehouse: Mapped[str] = mapped_column(String(40), default="Columbus, OH")

    product: Mapped[Product] = relationship(back_populates="inventory")

    @property
    def quantity_available(self) -> int:
        """Stock that can actually be promised to a new order.

        On-hand minus what is already committed to existing orders. This is the
        number the agent is allowed to quote; on-hand alone would overpromise.
        """
        return max(self.quantity_on_hand - self.quantity_allocated, 0)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False))
    customer_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    customer: Mapped[Customer] = relationship(back_populates="orders")
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.line_number",
    )
    shipments: Mapped[list[Shipment]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (UniqueConstraint("purchase_order_id", "line_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    line_number: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[LineStatus] = mapped_column(
        Enum(LineStatus, native_enum=False), default=LineStatus.OPEN
    )
    shipment_id: Mapped[int | None] = mapped_column(ForeignKey("shipments.id"), nullable=True)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    shipment: Mapped[Shipment | None] = relationship(
        back_populates="lines", foreign_keys=[shipment_id]
    )


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    carrier: Mapped[str] = mapped_column(String(40))
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus, native_enum=False))
    estimated_ship_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(60), nullable=True)

    order: Mapped[PurchaseOrder] = relationship(back_populates="shipments")
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="shipment", foreign_keys=[PurchaseOrderLine.shipment_id]
    )


class Rfq(Base):
    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[RfqStatus] = mapped_column(
        Enum(RfqStatus, native_enum=False), default=RfqStatus.SUBMITTED
    )
    notes: Mapped[str | None] = mapped_column(String(600), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="voice_agent")
    # Caller-supplied key used to make RFQ creation idempotent: a retried tool
    # call with the same key returns the original RFQ instead of a duplicate.
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="rfqs")
    lines: Mapped[list[RfqLine]] = relationship(
        back_populates="rfq", cascade="all, delete-orphan", order_by="RfqLine.line_number"
    )


class RfqLine(Base):
    __tablename__ = "rfq_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"))
    line_number: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"))
    quantity: Mapped[int] = mapped_column(Integer)

    rfq: Mapped[Rfq] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class AuditEvent(Base):
    """Append-only record of every attempted state change.

    Rejected writes are recorded too. "The agent tried to do X and the API said
    no" is exactly the evidence needed to show a guardrail actually fired.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(16))  # "success" | "rejected"
    source: Mapped[str] = mapped_column(String(32), default="voice_agent")
    conversation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
