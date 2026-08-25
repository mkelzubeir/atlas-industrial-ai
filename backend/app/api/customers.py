"""Customer lookup endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import fault_gate
from app.db import get_session
from app.logging_config import log_event
from app.schemas import CustomerSearchResponse
from app.services import customers

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get(
    "/search",
    response_model=CustomerSearchResponse,
    summary="Find a customer account by company name, contact, account number or email",
)
def search(
    query: str = Query(..., min_length=1, description="Company name, contact name, or account number."),
    limit: int = Query(5, ge=1, le=20),
    session: Session = Depends(get_session),
    _fault: None = Depends(fault_gate("customers")),
) -> CustomerSearchResponse:
    result = customers.search_customers(session, query, limit=limit)
    log_event(
        "tool.search_customers",
        query=query,
        match_count=result["match_count"],
        resolved=result["resolved"],
    )
    return CustomerSearchResponse.model_validate(result)
