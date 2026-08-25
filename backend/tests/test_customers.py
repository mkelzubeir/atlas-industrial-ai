"""Customer identification."""

from __future__ import annotations


def _search(client, query: str) -> dict:
    response = client.get("/api/customers/search", params={"query": query})
    assert response.status_code == 200
    return response.json()


def test_company_name_resolves_to_one_account(client):
    body = _search(client, "northstar")
    assert body["resolved"] is True
    assert body["match_count"] == 1
    assert body["customers"][0]["account_number"] == "NM-4471"
    assert body["customers"][0]["contact_name"] == "Ahmed Hassan"


def test_contact_name_also_resolves(client):
    body = _search(client, "Ahmed")
    assert body["resolved"] is True
    assert body["customers"][0]["company_name"] == "Northstar Manufacturing"


def test_account_number_resolves(client):
    body = _search(client, "NM-4471")
    assert body["resolved"] is True


def test_unknown_customer_returns_no_matches(client):
    body = _search(client, "Wayne Enterprises")
    assert body["match_count"] == 0
    assert body["resolved"] is False


def test_credit_hold_status_is_visible(client):
    body = _search(client, "Cedar Industrial")
    assert body["customers"][0]["status"] == "on_hold"
