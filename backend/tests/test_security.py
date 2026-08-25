"""The authentication boundary."""

from __future__ import annotations

from app.config import get_settings


def test_no_key_configured_means_open_access(client):
    """Local development runs with no configuration at all."""
    assert client.get("/api/orders/1847").status_code == 200


def test_configured_key_is_required(monkeypatch, client):
    monkeypatch.setenv("ATLAS_API_KEY", "s3cret-demo-key")
    get_settings.cache_clear()
    try:
        unauthenticated = client.get("/api/orders/1847")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["error"]["code"] == "UNAUTHORIZED"

        wrong = client.get("/api/orders/1847", headers={"X-Atlas-Api-Key": "wrong"})
        assert wrong.status_code == 401

        correct = client.get("/api/orders/1847", headers={"X-Atlas-Api-Key": "s3cret-demo-key"})
        assert correct.status_code == 200
    finally:
        monkeypatch.delenv("ATLAS_API_KEY", raising=False)
        get_settings.cache_clear()


def test_writes_are_also_protected(monkeypatch, client):
    monkeypatch.setenv("ATLAS_API_KEY", "s3cret-demo-key")
    get_settings.cache_clear()
    try:
        response = client.patch(
            "/api/orders/1847/lines/2", json={"quantity": 200, "customer_confirmed": True}
        )
        assert response.status_code == 401
    finally:
        monkeypatch.delenv("ATLAS_API_KEY", raising=False)
        get_settings.cache_clear()


def test_health_is_unauthenticated(monkeypatch, client):
    """Probes must not need the secret."""
    monkeypatch.setenv("ATLAS_API_KEY", "s3cret-demo-key")
    get_settings.cache_clear()
    try:
        assert client.get("/health").status_code == 200
    finally:
        monkeypatch.delenv("ATLAS_API_KEY", raising=False)
        get_settings.cache_clear()


def test_error_responses_never_echo_the_secret(monkeypatch, client):
    monkeypatch.setenv("ATLAS_API_KEY", "s3cret-demo-key")
    get_settings.cache_clear()
    try:
        body = client.get("/api/orders/1847", headers={"X-Atlas-Api-Key": "wrong"}).text
        assert "s3cret-demo-key" not in body
    finally:
        monkeypatch.delenv("ATLAS_API_KEY", raising=False)
        get_settings.cache_clear()
