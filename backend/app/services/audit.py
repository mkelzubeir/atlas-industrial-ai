"""Audit trail for state-changing operations.

Both successful and rejected writes are recorded. A guardrail that fires
silently is indistinguishable from a guardrail that does not exist, so the
refusal path writes an event too -- that row is the evidence the rule held.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_config import log_event
from app.models import AuditEvent


def record(
    session: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    outcome: str,
    payload: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    source: str = "voice_agent",
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        outcome=outcome,
        payload=payload or {},
        conversation_id=conversation_id,
        source=source,
    )
    session.add(event)
    session.flush()

    log_event(
        "audit",
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        outcome=outcome,
        audit_event_id=event.id,
        **(payload or {}),
    )
    return event


def recent(session: Session, limit: int = 25) -> list[AuditEvent]:
    return list(
        session.scalars(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit))
    )
