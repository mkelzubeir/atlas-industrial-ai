"""Purchase-order lookup and shipment reads."""

from __future__ import annotations

import pytest


def test_lookup_known_order_returns_lines_and_customer(client):
    response = client.get("/api/orders/1847")
    assert response.status_code == 200

    body = response.json()
    assert body["po_number"] == "1847"
    assert body["status"] == "processing"
    assert body["order_modifiable"] is True
    assert body["customer"]["company_name"] == "Northstar Manufacturing"
    assert body["line_count"] == 3

    bolts = body["lines"][0]
    assert bolts["sku"] == "ATL-1030"
    assert bolts["quantity"] == 600
    assert bolts["shipment"]["estimated_ship_day"] == "Friday"


# "%231847" is "#1847" percent-encoded: a raw "#" in a URL is a fragment
# delimiter and never reaches the server.
@pytest.mark.parametrize("spoken", ["1847", "PO 1847", "po-1847", "%231847", " Order 1847 "])
def test_po_number_is_normalised(client, spoken):
    """Speech recognition produces all of these for the same order."""
    response = client.get(f"/api/orders/{spoken}")
    assert response.status_code == 200
    assert response.json()["po_number"] == "1847"


def test_unknown_order_returns_structured_not_found(client):
    response = client.get("/api/orders/9999")
    assert response.status_code == 404

    error = response.json()["error"]
    assert error["code"] == "ORDER_NOT_FOUND"
    # The message must be speakable as-is -- it is what the caller will hear.
    assert "9999" in error["message"]


def test_shipped_order_is_marked_not_modifiable(client):
    body = client.get("/api/orders/1260").json()
    assert body["status"] == "shipped"
    assert body["order_modifiable"] is False
    assert all(line["modifiable"] is False for line in body["lines"])
    assert "already shipped" in body["lines"][0]["modification_note"]


def test_cancelled_order_is_marked_not_modifiable(client):
    body = client.get("/api/orders/2001").json()
    assert body["status"] == "cancelled"
    assert body["order_modifiable"] is False
    assert all(line["modifiable"] is False for line in body["lines"])


def test_partially_shipped_order_separates_order_and_line_eligibility(client):
    """PO 1905 is the case that proves the two rules are independent."""
    body = client.get("/api/orders/1905").json()
    assert body["status"] == "processing"
    assert body["order_modifiable"] is True

    shipped_line, allocated_line, open_line = body["lines"]
    assert shipped_line["status"] == "shipped"
    assert shipped_line["modifiable"] is False
    assert allocated_line["modifiable"] is True
    assert "reduced but not increased" in allocated_line["modification_note"]
    assert open_line["modifiable"] is True
    assert open_line["modification_note"] is None


def test_shipments_endpoint_returns_dates_and_weekday(client):
    body = client.get("/api/orders/1847/shipments").json()
    assert body["shipment_count"] == 1

    shipment = body["shipments"][0]
    assert shipment["carrier"] == "UPS Ground"
    assert shipment["estimated_ship_day"] == "Friday"
    assert shipment["line_numbers"] == [1]


def test_shipments_for_unknown_order_is_not_found(client):
    assert client.get("/api/orders/9999/shipments").status_code == 404
