"""Product resolution and, more importantly, ambiguity detection."""

from __future__ import annotations


def _search(client, query: str) -> dict:
    response = client.get("/api/products/search", params={"query": query})
    assert response.status_code == 200
    return response.json()


def test_specific_description_resolves_to_one_sku(client):
    """EVAL-004: enough detail to act on."""
    body = _search(client, "M8 x 30 stainless socket-head screws")
    assert body["resolved"] is True
    assert body["match_count"] == 1
    assert body["products"][0]["sku"] == "ATL-1030"
    assert body["clarification_hint"] is None


def test_underspecified_fastener_is_ambiguous_by_length(client):
    """EVAL-003: four stainless M8 cap screws differ only by length."""
    body = _search(client, "M8 stainless socket head screws")
    assert body["resolved"] is False
    assert body["match_count"] == 4
    assert body["distinguishing_attributes"][0] == "length_mm"
    # The hint names the actual options so the agent can offer them.
    assert "20" in body["clarification_hint"] and "50" in body["clarification_hint"]

    skus = {p["sku"] for p in body["products"]}
    assert skus == {"ATL-1020", "ATL-1030", "ATL-1040", "ATL-1050"}
    # Zinc-plated and M10 variants must not be swept in.
    assert "ATL-1031" not in skus
    assert "ATL-1130" not in skus


def test_gloves_are_ambiguous_by_material(client):
    """EVAL-009: the demo's ambiguous RFQ line."""
    body = _search(client, "chemical resistant gloves")
    assert body["resolved"] is False
    assert body["match_count"] == 3
    assert body["distinguishing_attributes"][0] == "material"
    hint = body["clarification_hint"]
    assert "nitrile" in hint and "neoprene" in hint and "butyl" in hint


def test_naming_the_material_resolves_the_gloves(client):
    body = _search(client, "nitrile chemical resistant gloves")
    assert body["resolved"] is True
    assert body["products"][0]["sku"] == "ATL-2110"


def test_exact_sku_short_circuits_to_one_product(client):
    body = _search(client, "ATL-1030")
    assert body["resolved"] is True
    assert body["products"][0]["sku"] == "ATL-1030"


def test_unknown_product_returns_no_matches_rather_than_a_guess(client):
    body = _search(client, "flux capacitor")
    assert body["match_count"] == 0
    assert body["resolved"] is False
    assert body["products"] == []


def test_search_returns_distinguishing_attributes_only(client):
    """Attributes shared by every candidate are not worth asking about."""
    body = _search(client, "M8 stainless socket head screws")
    # All four are stainless, so material must not be offered as the question.
    assert "material" not in body["distinguishing_attributes"]


def test_empty_query_is_rejected_by_validation(client):
    response = client.get("/api/products/search", params={"query": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
