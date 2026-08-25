"""RFQ creation, including server-owned identifiers and idempotency."""

from __future__ import annotations

from sqlalchemy import select

from app.models import AuditEvent, Rfq


def test_creating_an_rfq_returns_a_server_generated_number(client, session):
    """EVAL-008. The number exists because a row was written."""
    response = client.post(
        "/api/rfqs",
        json={
            "customer_account_number": "NM-4471",
            "lines": [
                {"sku": "ATL-1030", "quantity": 300},
                {"sku": "ATL-2110", "quantity": 50},
            ],
        },
    )
    assert response.status_code == 201

    body = response.json()
    # Seed data ends at RFQ-1027, so the next one continues the sequence.
    assert body["rfq_number"] == "RFQ-1028"
    assert body["status"] == "submitted"
    assert body["customer"]["company_name"] == "Northstar Manufacturing"
    assert body["line_count"] == 2
    assert [line["sku"] for line in body["lines"]] == ["ATL-1030", "ATL-2110"]
    assert [line["quantity"] for line in body["lines"]] == [300, 50]

    stored = session.scalar(select(Rfq).where(Rfq.rfq_number == "RFQ-1028"))
    assert stored is not None
    assert stored.source == "voice_agent"


def test_rfq_creation_is_audited(client, session):
    client.post(
        "/api/rfqs",
        json={"customer_account_number": "NM-4471", "lines": [{"sku": "ATL-1030", "quantity": 300}]},
    )
    events = list(session.scalars(select(AuditEvent).where(AuditEvent.event_type == "rfq_created")))
    assert len(events) == 1
    assert events[0].outcome == "success"
    assert events[0].payload["rfq_number"] == "RFQ-1028"


def test_rfq_numbers_increment_across_requests(client):
    first = client.post(
        "/api/rfqs",
        json={"customer_account_number": "NM-4471", "lines": [{"sku": "ATL-1030", "quantity": 10}]},
    ).json()
    second = client.post(
        "/api/rfqs",
        json={"customer_account_number": "AF-2280", "lines": [{"sku": "ATL-1040", "quantity": 10}]},
    ).json()
    assert first["rfq_number"] == "RFQ-1028"
    assert second["rfq_number"] == "RFQ-1029"


def test_idempotency_key_prevents_a_duplicate_quote(client, session):
    """A retried tool call must not book the same quote twice."""
    payload = {
        "customer_account_number": "NM-4471",
        "lines": [{"sku": "ATL-1030", "quantity": 300}],
        "idempotency_key": "conv-abc-line-1",
    }
    first = client.post("/api/rfqs", json=payload).json()
    second = client.post("/api/rfqs", json=payload).json()

    assert first["rfq_number"] == second["rfq_number"]
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert session.scalar(select(Rfq).where(Rfq.rfq_number == first["rfq_number"])) is not None
    assert len(list(session.scalars(select(Rfq)))) == 4  # 3 seeded + 1 created


def test_unknown_sku_is_refused(client, session):
    response = client.post(
        "/api/rfqs",
        json={
            "customer_account_number": "NM-4471",
            "lines": [{"sku": "ATL-1030", "quantity": 10}, {"sku": "ATL-9999", "quantity": 5}],
        },
    )
    assert response.status_code == 404

    error = response.json()["error"]
    assert error["code"] == "PRODUCT_NOT_FOUND"
    assert error["details"]["missing_skus"] == ["ATL-9999"]
    # Nothing partial was written.
    assert len(list(session.scalars(select(Rfq)))) == 3


def test_unknown_customer_is_refused(client):
    response = client.post(
        "/api/rfqs",
        json={"customer_account_number": "ZZ-0000", "lines": [{"sku": "ATL-1030", "quantity": 10}]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"


def test_empty_lines_are_refused(client):
    response = client.post(
        "/api/rfqs", json={"customer_account_number": "NM-4471", "lines": []}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_zero_quantity_line_is_refused(client):
    response = client.post(
        "/api/rfqs",
        json={"customer_account_number": "NM-4471", "lines": [{"sku": "ATL-1030", "quantity": 0}]},
    )
    assert response.status_code == 422


def test_duplicate_sku_lines_are_refused(client):
    """Two lines for the same SKU is almost always a transcription slip."""
    response = client.post(
        "/api/rfqs",
        json={
            "customer_account_number": "NM-4471",
            "lines": [{"sku": "ATL-1030", "quantity": 100}, {"sku": "ATL-1030", "quantity": 200}],
        },
    )
    assert response.status_code == 422
    assert "ATL-1030" in response.json()["error"]["message"]


def test_on_hold_customer_gets_a_flagged_quote(client):
    """Cedar Industrial is on credit hold: capture the quote, flag the hold."""
    body = client.post(
        "/api/rfqs",
        json={"customer_account_number": "CI-8804", "lines": [{"sku": "ATL-1030", "quantity": 100}]},
    ).json()
    assert body["rfq_number"] == "RFQ-1028"
    assert "credit hold" in body["message"]


def test_existing_rfq_can_be_looked_up(client):
    body = client.get("/api/rfqs/RFQ-1025").json()
    assert body["rfq_number"] == "RFQ-1025"
    assert body["status"] == "quoted"


def test_unknown_rfq_is_not_found(client):
    response = client.get("/api/rfqs/RFQ-9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RFQ_NOT_FOUND"
