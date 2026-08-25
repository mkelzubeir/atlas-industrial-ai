"""RFQ creation.

Two things this endpoint is strict about:

* **The server owns the RFQ number.** The model is never told an identifier it
  could have invented. `RFQ-1028` exists because a row was written; if the write
  fails, there is no number to say out loud.

* **Every line must name a real SKU.** The agent has to resolve products through
  `search_products` first. Free-text lines would let an unresolved "M8 screws"
  slip onto a quote, which is exactly the ambiguity the catalog was built to
  surface.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import ErrorCode, not_found
from app.models import Customer, CustomerStatus, Product, Rfq, RfqLine, RfqStatus
from app.services import audit, customers

RFQ_NUMBER_PATTERN = re.compile(r"RFQ-(\d+)")
RFQ_NUMBER_START = 1000


def _next_rfq_number(session: Session) -> str:
    """Allocate the next RFQ number.

    Derived from the highest existing number rather than a row count, so a
    reset demo continues the sequence rather than colliding with a number the
    caller was already given.
    """
    highest = RFQ_NUMBER_START
    for (number,) in session.execute(select(Rfq.rfq_number)):
        match = RFQ_NUMBER_PATTERN.fullmatch(number or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"RFQ-{highest + 1}"


def _serialise(rfq: Rfq, *, idempotent_replay: bool, message: str) -> dict:
    return {
        "rfq_number": rfq.rfq_number,
        "status": rfq.status.value,
        "customer": rfq.customer,
        "created_at": rfq.created_at,
        "line_count": len(rfq.lines),
        "lines": [
            {
                "line_number": line.line_number,
                "sku": line.sku,
                "product_name": line.product.name,
                "quantity": line.quantity,
                "unit_of_measure": line.product.unit_of_measure,
            }
            for line in rfq.lines
        ],
        "notes": rfq.notes,
        "idempotent_replay": idempotent_replay,
        "message": message,
    }


def _load(session: Session, rfq_id: int) -> Rfq:
    return session.scalar(
        select(Rfq)
        .where(Rfq.id == rfq_id)
        .options(selectinload(Rfq.lines).selectinload(RfqLine.product), selectinload(Rfq.customer))
    )


def create_rfq(
    session: Session,
    *,
    customer_account_number: str,
    lines: list[dict],
    notes: str | None = None,
    conversation_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    # Replay an earlier identical request rather than double-booking a quote.
    # A voice tool call that times out and retries must not create two RFQs.
    if idempotency_key:
        existing = session.scalar(select(Rfq).where(Rfq.idempotency_key == idempotency_key))
        if existing is not None:
            rfq = _load(session, existing.id)
            return _serialise(
                rfq,
                idempotent_replay=True,
                message=(
                    f"That request was already submitted as {rfq.rfq_number}, so it was not "
                    "duplicated."
                ),
            )

    customer: Customer | None = customers.get_by_account_number(session, customer_account_number)
    if customer is None:
        raise not_found(
            ErrorCode.CUSTOMER_NOT_FOUND,
            f"There is no Atlas account with number {customer_account_number}.",
            customer_account_number=customer_account_number,
        )

    requested_skus = [line["sku"].strip().upper() for line in lines]
    found = {
        product.sku: product
        for product in session.scalars(select(Product).where(Product.sku.in_(requested_skus)))
    }
    missing = [sku for sku in requested_skus if sku not in found]
    if missing:
        raise not_found(
            ErrorCode.PRODUCT_NOT_FOUND,
            "These SKUs are not in the Atlas catalog: " + ", ".join(missing) + ".",
            missing_skus=missing,
        )

    rfq = Rfq(
        rfq_number=_next_rfq_number(session),
        customer_id=customer.id,
        status=RfqStatus.SUBMITTED,
        notes=notes,
        source="voice_agent",
        idempotency_key=idempotency_key,
    )
    session.add(rfq)
    session.flush()

    for index, line in enumerate(lines, start=1):
        session.add(
            RfqLine(
                rfq_id=rfq.id,
                line_number=index,
                sku=line["sku"].strip().upper(),
                quantity=int(line["quantity"]),
            )
        )
    session.flush()

    audit.record(
        session,
        event_type="rfq_created",
        entity_type="rfq",
        entity_id=rfq.rfq_number,
        outcome="success",
        conversation_id=conversation_id,
        payload={
            "rfq_number": rfq.rfq_number,
            "customer_account_number": customer.account_number,
            "lines": [{"sku": line["sku"].upper(), "quantity": line["quantity"]} for line in lines],
        },
    )
    session.commit()

    loaded = _load(session, rfq.id)
    line_count = len(loaded.lines)
    message = (
        f"Request for quote {loaded.rfq_number} has been created for "
        f"{customer.company_name} with {line_count} line"
        f"{'s' if line_count != 1 else ''}."
    )
    if customer.status is CustomerStatus.ON_HOLD:
        # Not a hard block: the quote is still worth capturing, but the caller
        # should hear that pricing needs a human before it can be committed.
        message += (
            " This account is currently on credit hold, so pricing will need to be released "
            "by an Atlas account manager before the quote is sent."
        )

    return _serialise(loaded, idempotent_replay=False, message=message)


def get_rfq(session: Session, rfq_number: str) -> dict:
    normalised = (rfq_number or "").strip().upper()
    if normalised.isdigit():
        normalised = f"RFQ-{normalised}"
    rfq = session.scalar(
        select(Rfq)
        .where(Rfq.rfq_number == normalised)
        .options(selectinload(Rfq.lines).selectinload(RfqLine.product), selectinload(Rfq.customer))
    )
    if rfq is None:
        raise not_found(
            ErrorCode.RFQ_NOT_FOUND,
            f"I could not find request for quote {normalised}.",
            rfq_number=normalised,
        )
    return _serialise(rfq, idempotent_replay=False, message=f"{rfq.rfq_number} is {rfq.status.value}.")
