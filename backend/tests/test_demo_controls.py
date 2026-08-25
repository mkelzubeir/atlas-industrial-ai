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
