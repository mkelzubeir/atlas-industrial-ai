"""Request-for-quote endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy.orm import Session

from app.api.deps import fault_gate
from app.db import get_session
from app.logging_config import log_event
from app.schemas import CreateRfqRequest, RfqResponse
from app.services import rfqs

router = APIRouter(prefix="/rfqs", tags=["rfqs"])


@router.post(
    "",
    response_model=RfqResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a request for quote from resolved SKUs",
)
def create(
    payload: CreateRfqRequest,
    session: Session = Depends(get_session),
    x_conversation_id: str | None = Header(default=None),
    _fault: None = Depends(fault_gate("rfqs")),
) -> RfqResponse:
    result = rfqs.create_rfq(
        session,
        customer_account_number=payload.customer_account_number,
        lines=[line.model_dump() for line in payload.lines],
        notes=payload.notes,
        conversation_id=payload.conversation_id or x_conversation_id,
        idempotency_key=payload.idempotency_key,
    )
    log_event(
        "tool.create_rfq",
        rfq_number=result["rfq_number"],
        customer_account_number=payload.customer_account_number,
        line_count=result["line_count"],
        idempotent_replay=result["idempotent_replay"],
    )
    return RfqResponse.model_validate(result)


@router.get("/{rfq_number}", response_model=RfqResponse, summary="Look up an existing RFQ")
def get(
    rfq_number: str = Path(..., description="RFQ number, e.g. RFQ-1028."),
    session: Session = Depends(get_session),
    _fault: None = Depends(fault_gate("rfqs")),
) -> RfqResponse:
    result = rfqs.get_rfq(session, rfq_number)
    log_event("tool.lookup_rfq", rfq_number=result["rfq_number"], status=result["status"])
    return RfqResponse.model_validate(result)
