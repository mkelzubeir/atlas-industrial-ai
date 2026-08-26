"""Demo-only control plane.

NOT PART OF THE BUSINESS API. Everything in this router is gated behind
`require_demo_mode`, which reads `ATLAS_DEMO_MODE`. A deployment with that flag
off returns 403 for all of it.

The separation is the point: a database-wiping endpoint and a fault injector are
legitimate for a reproducible demo and indefensible in production, so they live
behind an explicit switch rather than being quietly mixed in with real routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.logging_config import log_event
from app.schemas import DemoFaultRequest, DemoFaultResponse, DemoResetResponse
from app.security import require_demo_mode
from app.services import activity, audit, faults, snapshot
from seed.seed import reset_database

router = APIRouter(
    prefix="/demo",
    tags=["demo"],
    dependencies=[Depends(require_demo_mode)],
)


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    summary="[DEMO ONLY] Restore the synthetic database to its seeded state",
)
def reset(session: Session = Depends(get_session)) -> DemoResetResponse:
    faults.clear()
    activity.clear()
    restored = reset_database(session)
    log_event("demo.reset", **restored)
    return DemoResetResponse(
        status="ok",
        restored=restored,
        message="Atlas demo data restored to its seeded state.",
    )


@router.post(
    "/fault",
    response_model=DemoFaultResponse,
    summary="[DEMO ONLY] Arm a deliberate backend failure to test agent error handling",
)
def arm_fault(payload: DemoFaultRequest) -> DemoFaultResponse:
    if payload.target not in faults.VALID_TARGETS:
        from app.errors import ErrorCode, bad_request

        raise bad_request(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown fault target {payload.target!r}. "
            f"Valid targets: {', '.join(sorted(faults.VALID_TARGETS))}.",
            valid_targets=sorted(faults.VALID_TARGETS),
        )
    armed = faults.arm(payload.target, calls=payload.calls, mode=payload.mode)
    log_event("demo.fault_armed", **armed)
    return DemoFaultResponse(
        status="armed",
        armed=armed,
        message=f"The next {payload.calls} call(s) to {payload.target} will fail with mode "
        f"{payload.mode!r}.",
    )


@router.delete(
    "/fault",
    response_model=DemoFaultResponse,
    summary="[DEMO ONLY] Clear all armed faults",
)
def clear_faults() -> DemoFaultResponse:
    faults.clear()
    log_event("demo.faults_cleared")
    return DemoFaultResponse(status="cleared", armed={}, message="All armed faults cleared.")


@router.get(
    "/audit",
    summary="[DEMO ONLY] Recent audit events, for the Developer View",
)
def recent_audit(limit: int = 25, session: Session = Depends(get_session)) -> dict:
    events = audit.recent(session, limit=limit)
    return {
        "count": len(events),
        "events": [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "outcome": event.outcome,
                "source": event.source,
                "conversation_id": event.conversation_id,
                "payload": event.payload,
            }
            for event in events
        ],
    }


@router.get(
    "/activity",
    summary="[DEMO ONLY] Recent tool calls with their arguments, for the Developer View",
)
def recent_activity(
    conversation_id: str | None = None,
    since_seq: int = 0,
    limit: int = 50,
) -> dict:
    """Backend-side view of the tool calls made during a conversation.

    The ElevenLabs client SDK reports which tool ran and what it returned, but
    not the arguments the agent chose. Those are only visible here, so the
    Developer View merges this feed with the client-side events using the
    conversation id the agent forwards on every tool call.
    """
    entries = activity.recent(conversation_id, limit=limit, since_seq=since_seq)
    return {
        "count": len(entries),
        "latest_seq": entries[-1]["seq"] if entries else since_seq,
        "entries": entries,
    }


@router.get(
    "/database",
    summary="[DEMO ONLY] The whole synthetic environment, for the demo data browser",
)
def database(session: Session = Depends(get_session)) -> dict:
    """Everything in the synthetic world, in one read-only payload.

    Exists so a visitor can see what there is to ask about -- which orders
    exist, which products are deliberately ambiguous, what is out of stock.
    Without it the demo is a guessing game.

    A real distributor would never serve every customer's order book from one
    endpoint. That is precisely why this sits behind the demo gate.
    """
    return snapshot.build_snapshot(session)
