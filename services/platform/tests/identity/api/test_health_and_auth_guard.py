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

from app.main import app, identity_module
from app.platform_core.shared_kernel.utils import new_uuid7

client = TestClient(app)


def test_liveness_endpoint_reports_healthy() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_protected_route_without_authorization_header_is_rejected() -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_organization_and_team_reads_without_authorization_header_are_rejected() -> None:
    assert client.get(f"/api/v1/organizations/{_ORG_ID}").status_code == 401
    assert client.get(f"/api/v1/organizations/{_ORG_ID}/teams").status_code == 401
    assert client.get(f"/api/v1/teams/{_USER_ID}/members").status_code == 401


def test_org_a_cannot_read_org_b_organization_or_teams() -> None:
    org_a = new_uuid7()
    org_b = new_uuid7()
    token = identity_module.token_service.issue_access_token(
        user_id=new_uuid7(), org_id=org_a, scopes=[]
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/v1/organizations/{org_b}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/organizations/{org_b}/teams", headers=headers).status_code == 403


def test_protected_route_with_malformed_authorization_header_is_rejected() -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "NotBearer sometoken"})
    assert response.status_code == 401


def test_protected_route_with_garbage_bearer_token_is_rejected() -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401


def test_login_rejects_missing_required_fields() -> None:
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_login_rejects_when_neither_org_id_nor_org_slug_is_given() -> None:
    response = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "secret"})
    assert response.status_code == 422


def test_login_rejects_when_both_org_id_and_org_slug_are_given() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "org_id": "00000000-0000-0000-0000-000000000000", "org_slug": "acme",
            "email": "a@b.com", "password": "secret",
        },
    )
    assert response.status_code == 422


def test_suspend_user_without_authorization_header_is_rejected() -> None:
    """Regression test: this endpoint previously had no authentication
    dependency at all (see users_router.py) — anyone could suspend any
    user's account unauthenticated."""
    response = client.post(
        "/api/v1/users/00000000-0000-0000-0000-000000000000/suspend", params={"reason": "test"}
    )
    assert response.status_code == 401


def test_reactivate_user_without_authorization_header_is_rejected() -> None:
    response = client.post("/api/v1/users/00000000-0000-0000-0000-000000000000/reactivate")
    assert response.status_code == 401


_ORG_ID = "00000000-0000-0000-0000-000000000000"
_USER_ID = "00000000-0000-0000-0000-000000000001"


def test_list_roles_without_authorization_header_is_rejected() -> None:
    """Regression test: list_roles previously had no authentication
    dependency (and no permission gate — 'role:read' didn't even exist in
    the catalog) at all, so any org's custom role names and permission
    grants were readable by anyone, unauthenticated."""
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/roles")
    assert response.status_code == 401


def test_permission_matrix_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/permission-matrix")
    assert response.status_code == 401


def test_list_organization_members_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/members")
    assert response.status_code == 401


def test_get_organization_member_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/members/{_USER_ID}")
    assert response.status_code == 401


def test_update_organization_without_authorization_header_is_rejected() -> None:
    response = client.patch(f"/api/v1/organizations/{_ORG_ID}", json={"name": "New Name"})
    assert response.status_code == 401


def test_list_roles_for_member_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/members/{_USER_ID}/roles")
    assert response.status_code == 401
