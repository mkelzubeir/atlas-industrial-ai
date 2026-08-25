"""Pydantic request/response models -- the wire contract for the agent's tools.

These shapes are designed for a *listener*, not a dashboard. Three rules guided
them:

1. Send derived fields, not raw ones. The caller asks "is it shipping Friday?",
   so the response carries `estimated_ship_day: "Friday"` alongside the ISO
   date. Making the model do date arithmetic is a reliable way to get a
   confidently wrong answer.

2. Send decisions, not just data. `modifiable: false` plus a
   `modification_note` written in plain English means the agent does not have to
   re-derive the business rules it was told about in its prompt.

3. Send less. Tool results become LLM context on every turn, so responses stay
   trimmed to what a representative would actually need to answer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AtlasModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


class CustomerSummary(AtlasModel):
    account_number: str
    company_name: str
    contact_name: str
    email: str
    phone: str
    status: str


class CustomerSearchResponse(AtlasModel):
    query: str
    match_count: int
    resolved: bool = Field(
        description="True when exactly one customer matched and it is safe to act on."
    )
    customers: list[CustomerSummary]


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductSummary(AtlasModel):
    sku: str
    name: str
    description: str
    category: str
    unit_of_measure: str
    unit_price: float
    attributes: dict[str, Any]


class ProductSearchResponse(AtlasModel):
    query: str
    match_count: int
    resolved: bool = Field(
        description="True when exactly one product matched, so no clarification is needed."
    )
    distinguishing_attributes: list[str] = Field(
        default_factory=list,
        description=(
            "Attribute names on which the matches actually differ. This is the useful thing "
            "to ask the caller about; anything they share is not worth a question."
        ),
    )
    clarification_hint: str | None = Field(
        default=None,
        description="A ready-made suggestion for what to ask the caller when the match is ambiguous.",
    )
    products: list[ProductSummary]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class InventoryResponse(AtlasModel):
    sku: str
    product_name: str
    unit_of_measure: str
    quantity_available: int = Field(
        description="On-hand minus already-allocated. This is the number that may be promised."
    )
    quantity_on_hand: int
    quantity_allocated: int
    warehouse: str
    expected_restock_date: date | None = None
    requested_quantity: int | None = None
    can_fulfil: bool | None = Field(
        default=None,
        description="Present only when requested_quantity was supplied.",
    )
    shortfall: int | None = Field(
        default=None, description="Units short of requested_quantity, when it was supplied."
    )


# ---------------------------------------------------------------------------
# Orders and shipments
# ---------------------------------------------------------------------------


class ShipmentSummary(AtlasModel):
    shipment_id: int
    carrier: str
    status: str
    estimated_ship_date: date | None = None
    estimated_ship_day: str | None = Field(
        default=None, description='Weekday name of estimated_ship_date, e.g. "Friday".'
    )
    estimated_delivery_date: date | None = None
    estimated_delivery_day: str | None = None
    tracking_number: str | None = None
    line_numbers: list[int] = Field(
        default_factory=list, description="Order lines travelling on this shipment."
    )


class OrderLineSummary(AtlasModel):
    line_number: int
    sku: str
    product_name: str
    quantity: int
    unit_of_measure: str
    unit_price: float
    status: str
    modifiable: bool
    modification_note: str | None = Field(
        default=None,
        description="Plain-English reason the line cannot be changed, or the limits on changing it.",
    )
    shipment: ShipmentSummary | None = None


class OrderResponse(AtlasModel):
    po_number: str
    status: str
    order_modifiable: bool
    customer: CustomerSummary
    customer_reference: str | None = None
    created_at: datetime
    line_count: int
    lines: list[OrderLineSummary]
    shipments: list[ShipmentSummary]


class ShipmentsResponse(AtlasModel):
    po_number: str
    order_status: str
    shipment_count: int
    shipments: list[ShipmentSummary]


# ---------------------------------------------------------------------------
# Order modification (write)
# ---------------------------------------------------------------------------


class UpdateOrderLineRequest(BaseModel):
    quantity: int = Field(description="The new quantity for this line. Must be 1 or more.")
    customer_confirmed: bool = Field(
        description=(
            "Must be true. The agent asserts that the caller explicitly approved this exact "
            "change immediately before the call was made."
        )
    )
    expected_current_quantity: int | None = Field(
        default=None,
        description=(
            "Optional. The quantity the agent believes the line holds right now. When supplied "
            "and it does not match, the write is refused instead of silently overwriting a "
            "change made since the order was read."
        ),
    )
    conversation_id: str | None = Field(
        default=None, description="ElevenLabs conversation id, recorded on the audit event."
    )
    reason: str | None = Field(
        default=None, max_length=300, description="Short note on why the caller wanted the change."
    )

    @field_validator("customer_confirmed")
    @classmethod
    def _must_be_confirmed(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "customer_confirmed must be true; ask the caller to approve the change first"
            )
        return value


class UpdateOrderLineResponse(AtlasModel):
    po_number: str
    line_number: int
    sku: str
    product_name: str
    previous_quantity: int
    new_quantity: int
    line_status: str
    order_status: str
    audit_event_id: int
    message: str = Field(description="A one-sentence summary the agent can say aloud.")


# ---------------------------------------------------------------------------
# RFQs (write)
# ---------------------------------------------------------------------------


class RfqLineRequest(BaseModel):
    sku: str = Field(description="An exact Atlas SKU, resolved beforehand via search_products.")
    quantity: int = Field(gt=0, description="Units requested. Must be 1 or more.")


class CreateRfqRequest(BaseModel):
    customer_account_number: str = Field(
        description="Atlas account number of the requesting customer, e.g. NM-4471."
    )
    lines: list[RfqLineRequest] = Field(min_length=1, description="At least one resolved line.")
    notes: str | None = Field(default=None, max_length=600)
    conversation_id: str | None = None
    idempotency_key: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "Optional. Reusing a key returns the RFQ created the first time instead of "
            "creating a duplicate, so a retried tool call cannot double-book a quote."
        ),
    )

    @field_validator("lines")
    @classmethod
    def _no_duplicate_skus(cls, lines: list[RfqLineRequest]) -> list[RfqLineRequest]:
        seen = [line.sku.upper() for line in lines]
        duplicates = {sku for sku in seen if seen.count(sku) > 1}
        if duplicates:
            raise ValueError(
                f"each SKU may appear only once; combine the quantities for {', '.join(sorted(duplicates))}"
            )
        return lines


class RfqLineSummary(AtlasModel):
    line_number: int
    sku: str
    product_name: str
    quantity: int
    unit_of_measure: str


class RfqResponse(AtlasModel):
    rfq_number: str
    status: str
    customer: CustomerSummary
    created_at: datetime
    line_count: int
    lines: list[RfqLineSummary]
    notes: str | None = None
    idempotent_replay: bool = Field(
        default=False,
        description="True when this RFQ already existed and was returned rather than created.",
    )
    message: str


# ---------------------------------------------------------------------------
# Demo control
# ---------------------------------------------------------------------------


class DemoResetResponse(BaseModel):
    status: str
    restored: dict[str, int]
    message: str


class DemoFaultRequest(BaseModel):
    target: str = Field(
        description="Which tool endpoint to fail: inventory, products, orders, shipments, rfqs, or all."
    )
    calls: int = Field(default=1, ge=1, le=50, description="How many calls to fail before clearing.")
    mode: str = Field(default="error", description="'error' for a 503, 'timeout' for a slow response.")


class DemoFaultResponse(BaseModel):
    status: str
    armed: dict[str, Any]
    message: str
