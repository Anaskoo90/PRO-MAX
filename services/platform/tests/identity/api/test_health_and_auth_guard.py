"""
API-level smoke tests that don't require a live database or broker —
TestClient is deliberately used without the `with` context-manager form,
so Starlette never triggers the app's lifespan (which calls
identity_module.seed(), a real DB hit) for these.

Full authenticated-flow API tests (register -> login -> call a protected
route) belong in tests/identity/integration, since they need the whole
stack running.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_endpoint_reports_healthy() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_protected_route_without_authorization_header_is_rejected() -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_protected_route_with_malformed_authorization_header_is_rejected() -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "NotBearer sometoken"})
    assert response.status_code == 401


def test_protected_route_with_garbage_bearer_token_is_rejected() -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401


def test_login_rejects_missing_required_fields() -> None:
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422
