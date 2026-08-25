"""Demo-only endpoints: reset, fault injection, and the audit feed."""

from __future__ import annotations

from app.config import get_settings


def test_reset_restores_a_modified_order(client):
    client.patch("/api/orders/1847/lines/2", json={"quantity": 200, "customer_confirmed": True})
    assert client.get("/api/orders/1847").json()["lines"][1]["quantity"] == 200

    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert response.json()["restored"]["purchase_orders"] == 10

    assert client.get("/api/orders/1847").json()["lines"][1]["quantity"] == 500


def test_reset_clears_created_rfqs(client):
    client.post(
        "/api/rfqs",
        json={"customer_account_number": "NM-4471", "lines": [{"sku": "ATL-1030", "quantity": 10}]},
    )
    assert client.get("/api/rfqs/RFQ-1028").status_code == 200

    client.post("/api/demo/reset")
    assert client.get("/api/rfqs/RFQ-1028").status_code == 404


def test_reset_clears_the_audit_trail(client):
    client.patch("/api/orders/1847/lines/2", json={"quantity": 200, "customer_confirmed": True})
    assert client.get("/api/demo/audit").json()["count"] >= 1

    client.post("/api/demo/reset")
    assert client.get("/api/demo/audit").json()["count"] == 0


def test_audit_feed_shows_rejections_as_well_as_successes(client):
    client.patch("/api/orders/1260/lines/1", json={"quantity": 10, "customer_confirmed": True})

    events = client.get("/api/demo/audit").json()["events"]
    assert len(events) == 1
    assert events[0]["outcome"] == "rejected"
    assert events[0]["payload"]["rejection_code"] == "ORDER_NOT_MODIFIABLE"


# ---------------------------------------------------------------------------
# Fault injection -- the mechanism behind EVAL-010.
# ---------------------------------------------------------------------------


def test_armed_fault_makes_the_next_call_fail(client):
    client.post("/api/demo/fault", json={"target": "inventory", "calls": 1})

    failed = client.get("/api/inventory/ATL-1030")
    assert failed.status_code == 503

    error = failed.json()["error"]
    assert error["code"] == "SERVICE_UNAVAILABLE"
    # The message has to be speakable: the agent says this instead of guessing.
    assert "can't retrieve" in error["message"]


def test_fault_clears_itself_after_the_armed_number_of_calls(client):
    client.post("/api/demo/fault", json={"target": "inventory", "calls": 1})
    assert client.get("/api/inventory/ATL-1030").status_code == 503
    assert client.get("/api/inventory/ATL-1030").status_code == 200


def test_fault_targets_only_the_named_endpoint(client):
    client.post("/api/demo/fault", json={"target": "inventory", "calls": 1})
    assert client.get("/api/orders/1847").status_code == 200
    assert client.get("/api/inventory/ATL-1030").status_code == 503


def test_all_target_fails_every_endpoint(client):
    client.post("/api/demo/fault", json={"target": "all", "calls": 2})
    assert client.get("/api/orders/1847").status_code == 503
    assert client.get("/api/products/search", params={"query": "bolt"}).status_code == 503
    assert client.get("/api/orders/1847").status_code == 200


def test_faults_can_be_cleared_manually(client):
    client.post("/api/demo/fault", json={"target": "orders", "calls": 5})
    client.delete("/api/demo/fault")
    assert client.get("/api/orders/1847").status_code == 200


def test_reset_also_clears_armed_faults(client):
    client.post("/api/demo/fault", json={"target": "orders", "calls": 5})
    client.post("/api/demo/reset")
    assert client.get("/api/orders/1847").status_code == 200


def test_unknown_fault_target_is_rejected(client):
    response = client.post("/api/demo/fault", json={"target": "warp-core", "calls": 1})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# The demo gate itself
# ---------------------------------------------------------------------------


def test_demo_endpoints_are_refused_when_demo_mode_is_off(monkeypatch, client):
    """A deployment with demo mode off must not expose a database wipe."""
    monkeypatch.setenv("ATLAS_DEMO_MODE", "false")
    get_settings.cache_clear()
    try:
        response = client.post("/api/demo/reset")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "DEMO_MODE_DISABLED"
    finally:
        monkeypatch.delenv("ATLAS_DEMO_MODE", raising=False)
        get_settings.cache_clear()


def test_business_endpoints_still_work_when_demo_mode_is_off(monkeypatch, client):
    monkeypatch.setenv("ATLAS_DEMO_MODE", "false")
    get_settings.cache_clear()
    try:
        assert client.get("/api/orders/1847").status_code == 200
    finally:
        monkeypatch.delenv("ATLAS_DEMO_MODE", raising=False)
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Activity feed -- the backend half of the Developer View
# ---------------------------------------------------------------------------


def test_activity_feed_records_tool_calls_with_their_arguments(client):
    client.get("/api/orders/1847", headers={"X-Conversation-Id": "conv-1"})
    client.get(
        "/api/inventory/ATL-1030",
        params={"requested_quantity": 600},
        headers={"X-Conversation-Id": "conv-1"},
    )

    body = client.get("/api/demo/activity", params={"conversation_id": "conv-1"}).json()
    assert body["count"] == 2

    order_call, inventory_call = body["entries"]
    assert order_call["tool"] == "lookup_order"
    assert order_call["ok"] is True
    assert order_call["params"]["po_number"] == "1847"
    assert inventory_call["tool"] == "check_inventory"
    assert inventory_call["params"]["requested_quantity"] == 600
    assert inventory_call["duration_ms"] >= 0


def test_activity_feed_is_scoped_to_one_conversation(client):
    client.get("/api/orders/1847", headers={"X-Conversation-Id": "conv-a"})
    client.get("/api/orders/1260", headers={"X-Conversation-Id": "conv-b"})

    a = client.get("/api/demo/activity", params={"conversation_id": "conv-a"}).json()
    assert a["count"] == 1
    assert a["entries"][0]["params"]["po_number"] == "1847"


def test_activity_feed_records_failures_with_their_error_code(client):
    client.get("/api/orders/9999", headers={"X-Conversation-Id": "conv-err"})

    entry = client.get(
        "/api/demo/activity", params={"conversation_id": "conv-err"}
    ).json()["entries"][0]
    assert entry["ok"] is False
    assert entry["status_code"] == 404
    assert entry["error_code"] == "ORDER_NOT_FOUND"


def test_activity_feed_records_rejected_writes(client):
    client.patch(
        "/api/orders/1260/lines/1",
        json={"quantity": 10, "customer_confirmed": True},
        headers={"X-Conversation-Id": "conv-w"},
    )
    entry = client.get(
        "/api/demo/activity", params={"conversation_id": "conv-w"}
    ).json()["entries"][0]
    assert entry["error_code"] == "ORDER_NOT_MODIFIABLE"
    assert entry["method"] == "PATCH"


def test_activity_feed_supports_incremental_polling(client):
    client.get("/api/orders/1847", headers={"X-Conversation-Id": "conv-poll"})
    first = client.get("/api/demo/activity", params={"conversation_id": "conv-poll"}).json()

    client.get("/api/orders/1260", headers={"X-Conversation-Id": "conv-poll"})
    second = client.get(
        "/api/demo/activity",
        params={"conversation_id": "conv-poll", "since_seq": first["latest_seq"]},
    ).json()
    assert second["count"] == 1
    assert second["entries"][0]["params"]["po_number"] == "1260"


def test_demo_endpoints_are_not_recorded_as_tool_calls(client):
    client.get("/api/demo/audit", headers={"X-Conversation-Id": "conv-meta"})
    body = client.get("/api/demo/activity", params={"conversation_id": "conv-meta"}).json()
    assert body["count"] == 0


def test_failed_calls_are_still_labelled_with_their_tool(client):
    """A refusal is the most useful row in the Developer View.

    The route's own log line never runs when the handler raises, so the tool
    name has to come from the route itself.
    """
    client.patch(
        "/api/orders/1260/lines/1",
        json={"quantity": 60, "customer_confirmed": True},
        headers={"X-Conversation-Id": "conv-label"},
    )
    client.get("/api/orders/9999", headers={"X-Conversation-Id": "conv-label"})

    entries = client.get(
        "/api/demo/activity", params={"conversation_id": "conv-label"}
    ).json()["entries"]
    assert [e["tool"] for e in entries] == ["update_order_line", "lookup_order"]
    assert [e["error_code"] for e in entries] == ["ORDER_NOT_MODIFIABLE", "ORDER_NOT_FOUND"]


def test_successful_calls_keep_the_handlers_own_tool_name(client):
    """The route fallback must not override what the handler reported."""
    client.get("/api/orders/1847/shipments", headers={"X-Conversation-Id": "conv-ok"})
    entry = client.get(
        "/api/demo/activity", params={"conversation_id": "conv-ok"}
    ).json()["entries"][0]
    assert entry["tool"] == "lookup_shipment"
