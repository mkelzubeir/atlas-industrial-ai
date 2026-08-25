"""Customer lookup.

Identity here is deliberately lightweight -- this is a demo, not an
authentication system. What it does model is the *shape* of the check: before a
write, the agent must have resolved the caller to exactly one account, and that
account must own the order being changed.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Customer


def search_customers(session: Session, query: str, limit: int = 5) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": query, "match_count": 0, "resolved": False, "customers": []}

    like = f"%{query.lower()}%"
    statement = (
        select(Customer)
        .where(
            or_(
                Customer.company_name.ilike(like),
                Customer.contact_name.ilike(like),
                Customer.account_number.ilike(like),
                Customer.email.ilike(like),
            )
        )
        .order_by(Customer.company_name)
        .limit(limit)
    )
    customers = list(session.scalars(statement))
    return {
        "query": query,
        "match_count": len(customers),
        "resolved": len(customers) == 1,
        "customers": customers,
    }


def get_by_account_number(session: Session, account_number: str) -> Customer | None:
    return session.scalar(
        select(Customer).where(Customer.account_number.ilike(account_number.strip()))
    )
