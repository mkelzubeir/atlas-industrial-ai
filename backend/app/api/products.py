"""Product catalog endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import fault_gate
from app.db import get_session
from app.logging_config import log_event
from app.schemas import ProductSearchResponse
from app.services import products

router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "/search",
    response_model=ProductSearchResponse,
    summary="Resolve a spoken product description to Atlas SKUs",
)
def search(
    query: str = Query(..., min_length=1, description='Free text, e.g. "M8 stainless socket head screws".'),
    limit: int = Query(6, ge=1, le=20),
    session: Session = Depends(get_session),
    _fault: None = Depends(fault_gate("products")),
) -> ProductSearchResponse:
    result = products.search_products(session, query, limit=limit)
    log_event(
        "tool.search_products",
        query=query,
        match_count=result["match_count"],
        resolved=result["resolved"],
        skus=[p.sku for p in result["products"]],
    )
    return ProductSearchResponse.model_validate(result)
