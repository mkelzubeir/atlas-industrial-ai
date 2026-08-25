"""Inventory availability."""

from __future__ import annotations


def test_inventory_reports_available_not_just_on_hand(client):
    body = client.get("/api/inventory/ATL-1030").json()
    assert body["quantity_on_hand"] == 2850
    assert body["quantity_allocated"] == 1100
    # Available is what may actually be promised.
    assert body["quantity_available"] == 1750


def test_requested_quantity_gets_a_direct_answer(client):
    """EVAL-004: 'do you have 600?' should be answered, not just described."""
    body = client.get(
        "/api/inventory/ATL-1030", params={"requested_quantity": 600}
    ).json()
    assert body["can_fulfil"] is True
    assert body["shortfall"] == 0


def test_shortfall_is_reported_when_stock_is_insufficient(client):
    body = client.get("/api/inventory/ATL-2110", params={"requested_quantity": 300}).json()
    assert body["can_fulfil"] is False
    assert body["quantity_available"] == 140
    assert body["shortfall"] == 160
    assert body["expected_restock_date"] is not None


def test_fully_backordered_sku_reports_zero_with_a_restock_date(client):
    body = client.get("/api/inventory/ATL-3206", params={"requested_quantity": 5}).json()
    assert body["quantity_available"] == 0
    assert body["can_fulfil"] is False
    assert body["expected_restock_date"] is not None


def test_sku_is_case_insensitive(client):
    assert client.get("/api/inventory/atl-1030").json()["sku"] == "ATL-1030"


def test_unknown_sku_is_not_found(client):
    response = client.get("/api/inventory/ATL-9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
