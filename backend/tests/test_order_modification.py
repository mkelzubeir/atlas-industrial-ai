"""Server-side enforcement of the order-modification rules.

These are the tests that matter most. Every one of them asserts something the
system prompt *also* says -- and the point is that the prompt is not what makes
it true. Each case sends a request an agent could plausibly make and checks that
the API decides the outcome on its own.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import AuditEvent, PurchaseOrder, PurchaseOrderLine


def _line_quantity(session, po_number: str, line_number: int) -> int:
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    line = session.scalar(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == order.id,
            PurchaseOrderLine.line_number == line_number,
        )
    )
    return line.quantity


def _audit_events(session, event_type: str | None = None) -> list[AuditEvent]:
    statement = select(AuditEvent)
    if event_type:
        statement = statement.where(AuditEvent.event_type == event_type)
    return list(session.scalars(statement))


# ---------------------------------------------------------------------------
# The permitted path
# ---------------------------------------------------------------------------


def test_reducing_an_open_line_succeeds_and_is_audited(client, session):
    """The flagship demo write: 500 washers down to 200."""
    response = client.patch(
        "/api/orders/1847/lines/2",
        json={"quantity": 200, "customer_confirmed": True, "reason": "reduced requirement"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["previous_quantity"] == 500
    assert body["new_quantity"] == 200
    assert body["sku"] == "ATL-1310"

    assert _line_quantity(session, "1847", 2) == 200

    events = _audit_events(session, "order_line_quantity_changed")
    assert len(events) == 1
    assert events[0].outcome == "success"
    assert events[0].payload["previous_quantity"] == 500
    assert events[0].payload["new_quantity"] == 200
    assert events[0].payload["customer_confirmed"] is True


def test_reducing_an_allocated_line_releases_inventory(client, session):
    """Reducing an allocated line must give the committed stock back."""
    from app.models import Inventory

    before = session.get(Inventory, "ATL-1030").quantity_allocated

    response = client.patch(
        "/api/orders/1847/lines/1", json={"quantity": 400, "customer_confirmed": True}
    )
    assert response.status_code == 200

    session.expire_all()
    after = session.get(Inventory, "ATL-1030").quantity_allocated
    assert after == before - 200


def test_increasing_an_open_line_within_stock_succeeds(client, session):
    response = client.patch(
        "/api/orders/1847/lines/2", json={"quantity": 900, "customer_confirmed": True}
    )
    assert response.status_code == 200
    assert _line_quantity(session, "1847", 2) == 900


# ---------------------------------------------------------------------------
# Refusals. Each asserts: correct code, no mutation, and an audit trail.
# ---------------------------------------------------------------------------


def test_shipped_order_modification_is_rejected(client, session):
    """EVAL-006. Even if the agent tries anyway, the API refuses."""
    response = client.patch(
        "/api/orders/1260/lines/1", json={"quantity": 10, "customer_confirmed": True}
    )
    assert response.status_code == 409

    error = response.json()["error"]
    assert error["code"] == "ORDER_NOT_MODIFIABLE"
    assert "already shipped" in error["message"]

    assert _line_quantity(session, "1260", 1) == 40  # unchanged

    rejections = _audit_events(session, "order_line_quantity_change_rejected")
    assert len(rejections) == 1
    assert rejections[0].outcome == "rejected"
    assert rejections[0].payload["rejection_code"] == "ORDER_NOT_MODIFIABLE"


def test_cancelled_order_modification_is_rejected(client, session):
    response = client.patch(
        "/api/orders/2001/lines/1", json={"quantity": 5, "customer_confirmed": True}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_NOT_MODIFIABLE"
    assert _line_quantity(session, "2001", 1) == 10


def test_shipped_line_on_open_order_is_rejected(client, session):
    """The order is still editable; this particular line is not."""
    response = client.patch(
        "/api/orders/1905/lines/1", json={"quantity": 60, "customer_confirmed": True}
    )
    assert response.status_code == 409

    error = response.json()["error"]
    assert error["code"] == "LINE_NOT_MODIFIABLE"
    assert _line_quantity(session, "1905", 1) == 120


def test_increasing_an_allocated_line_is_rejected(client, session):
    """Allocated stock may be released, never claimed."""
    response = client.patch(
        "/api/orders/1847/lines/1", json={"quantity": 800, "customer_confirmed": True}
    )
    assert response.status_code == 409

    error = response.json()["error"]
    assert error["code"] == "QUANTITY_INCREASE_NOT_ALLOWED"
    assert "reduced but not increased" in error["message"]
    assert _line_quantity(session, "1847", 1) == 600


def test_increase_beyond_available_stock_is_rejected(client, session):
    """PO 1905 line 3 is open; only limited shop-towel stock is free."""
    response = client.patch(
        "/api/orders/1905/lines/3", json={"quantity": 5000, "customer_confirmed": True}
    )
    assert response.status_code == 409

    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_INVENTORY"
    assert "quantity_available" in error["details"]
    assert _line_quantity(session, "1905", 3) == 8


def test_zero_quantity_is_rejected_rather_than_treated_as_cancellation(client, session):
    response = client.patch(
        "/api/orders/1847/lines/2", json={"quantity": 0, "customer_confirmed": True}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUANTITY"
    assert _line_quantity(session, "1847", 2) == 500


def test_absurd_quantity_is_rejected(client, session):
    """Guards against a mis-transcribed number becoming a real order."""
    response = client.patch(
        "/api/orders/1847/lines/2", json={"quantity": 999_999, "customer_confirmed": True}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUANTITY"
    assert _line_quantity(session, "1847", 2) == 500


def test_unconfirmed_write_is_refused(client, session):
    """EVAL-007. The confirmation flag is part of the wire contract."""
    response = client.patch(
        "/api/orders/1847/lines/2", json={"quantity": 200, "customer_confirmed": False}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _line_quantity(session, "1847", 2) == 500


def test_missing_confirmation_field_is_refused(client, session):
    response = client.patch("/api/orders/1847/lines/2", json={"quantity": 200})
    assert response.status_code == 422
    assert _line_quantity(session, "1847", 2) == 500


def test_unknown_line_number_is_not_found(client):
    response = client.patch(
        "/api/orders/1847/lines/9", json={"quantity": 10, "customer_confirmed": True}
    )
    assert response.status_code == 404

    error = response.json()["error"]
    assert error["code"] == "LINE_NOT_FOUND"
    assert error["details"]["available_line_numbers"] == [1, 2, 3]


def test_unknown_order_is_not_found(client):
    response = client.patch(
        "/api/orders/9999/lines/1", json={"quantity": 10, "customer_confirmed": True}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


# ---------------------------------------------------------------------------
# Concurrency and idempotency
# ---------------------------------------------------------------------------


def test_stale_expected_quantity_blocks_a_blind_overwrite(client, session):
    """The agent read 500, but the line moved underneath it."""
    client.patch("/api/orders/1847/lines/2", json={"quantity": 300, "customer_confirmed": True})

    response = client.patch(
        "/api/orders/1847/lines/2",
        json={"quantity": 200, "customer_confirmed": True, "expected_current_quantity": 500},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LINE_NOT_MODIFIABLE"
    assert _line_quantity(session, "1847", 2) == 300


def test_matching_expected_quantity_allows_the_write(client, session):
    response = client.patch(
        "/api/orders/1847/lines/2",
        json={"quantity": 200, "customer_confirmed": True, "expected_current_quantity": 500},
    )
    assert response.status_code == 200
    assert _line_quantity(session, "1847", 2) == 200


def test_setting_the_same_quantity_reports_a_no_op(client, session):
    response = client.patch(
        "/api/orders/1847/lines/2", json={"quantity": 500, "customer_confirmed": True}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["previous_quantity"] == body["new_quantity"] == 500
    assert "nothing changed" in body["message"]
    assert _audit_events(session, "order_line_quantity_changed") == []
