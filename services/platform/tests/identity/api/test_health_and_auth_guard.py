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

from app.identity.presentation import deps
from app.main import app, identity_module
from app.platform_core.shared_kernel.utils import new_uuid7
from fastapi.testclient import TestClient

client = TestClient(app)


def test_liveness_endpoint_reports_healthy() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_protected_route_without_authorization_header_is_rejected() -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_direct_user_registration_cannot_bypass_organization_invitations() -> None:
    response = client.post(
        "/api/v1/users/register",
        json={
            "org_id": str(new_uuid7()),
            "email": "uninvited@example.com",
            "password": "Uninvited-Password-13!",
            "display_name": "Uninvited User",
        },
    )
    assert response.status_code == 404

    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/users/register" not in paths
    assert "/api/v1/organizations/register" in paths
    assert "/api/v1/invitations/accept" in paths


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


class _AllowAllPermissions:
    async def assert_permission(self, **kwargs) -> None:
        return None


class _InvitationServiceSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def invite_member(self, **kwargs):
        self.calls.append(("create", kwargs))
        raise AssertionError("cross-tenant create reached the application service")

    async def list_pending(self, **kwargs):
        self.calls.append(("list", kwargs))
        return []

    async def revoke_invitation(self, **kwargs) -> None:
        self.calls.append(("revoke", kwargs))


def _invitation_test_headers(org_id) -> dict[str, str]:
    token = identity_module.token_service.issue_access_token(
        user_id=new_uuid7(), org_id=org_id, scopes=[]
    )
    return {"Authorization": f"Bearer {token}"}


def test_invitation_routes_reject_cross_tenant_path_ids_before_service_access() -> None:
    org_a = new_uuid7()
    org_b = new_uuid7()
    role_id = new_uuid7()
    invitation_id = new_uuid7()
    service = _InvitationServiceSpy()
    app.dependency_overrides[deps.get_permission_evaluator] = lambda: _AllowAllPermissions()
    app.dependency_overrides[deps.get_organization_invitation_service] = lambda: service

    try:
        headers = _invitation_test_headers(org_a)
        create = client.post(
            f"/api/v1/organizations/{org_b}/invitations",
            headers=headers,
            json={"email": "invitee@example.com", "role_id": str(role_id)},
        )
        listing = client.get(f"/api/v1/organizations/{org_b}/invitations", headers=headers)
        revoke = client.delete(
            f"/api/v1/organizations/{org_b}/invitations/{invitation_id}", headers=headers
        )
    finally:
        app.dependency_overrides.pop(deps.get_permission_evaluator, None)
        app.dependency_overrides.pop(deps.get_organization_invitation_service, None)

    assert (create.status_code, listing.status_code, revoke.status_code) == (403, 403, 403)
    assert service.calls == []


def test_authorized_same_tenant_invitation_listing_still_works() -> None:
    org_id = new_uuid7()
    service = _InvitationServiceSpy()
    app.dependency_overrides[deps.get_permission_evaluator] = lambda: _AllowAllPermissions()
    app.dependency_overrides[deps.get_organization_invitation_service] = lambda: service

    try:
        response = client.get(
            f"/api/v1/organizations/{org_id}/invitations",
            headers=_invitation_test_headers(org_id),
        )
    finally:
        app.dependency_overrides.pop(deps.get_permission_evaluator, None)
        app.dependency_overrides.pop(deps.get_organization_invitation_service, None)

    assert response.status_code == 200
    assert response.json() == {"data": []}
    assert service.calls[0][0] == "list"
    assert service.calls[0][1]["org_id"] == org_id


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


def test_disabled_oauth_provider_returns_not_found_instead_of_internal_error() -> None:
    response = client.get(
        "/api/v1/auth/oauth2/discord/authorize",
        params={"org_id": str(new_uuid7())},
    )

    assert response.status_code == 404


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


def test_revoke_trusted_device_without_authorization_header_is_rejected() -> None:
    response = client.delete(
        "/api/v1/users/me/trusted-devices/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


class _DeviceTrustServiceSpy:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def revoke_device(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _SecurityServiceSpy:
    def __init__(self) -> None:
        self.device_trust_service = _DeviceTrustServiceSpy()


def test_revoke_trusted_device_is_scoped_to_the_authenticated_user() -> None:
    org_id = new_uuid7()
    user_id = new_uuid7()
    device_id = new_uuid7()
    token = identity_module.token_service.issue_access_token(
        user_id=user_id, org_id=org_id, scopes=[]
    )
    service = _SecurityServiceSpy()
    app.dependency_overrides[deps.get_security_service] = lambda: service

    try:
        response = client.delete(
            f"/api/v1/users/me/trusted-devices/{device_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(deps.get_security_service, None)

    assert response.status_code == 204
    assert service.device_trust_service.calls == [{"user_id": user_id, "device_id": device_id}]


class _AuditLogQueryServiceSpy:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def list_for_org(self, **kwargs):
        self.calls.append(kwargs)
        return []


def test_audit_log_route_rejects_cross_tenant_path_before_querying() -> None:
    org_a = new_uuid7()
    org_b = new_uuid7()
    service = _AuditLogQueryServiceSpy()
    app.dependency_overrides[deps.get_permission_evaluator] = lambda: _AllowAllPermissions()
    app.dependency_overrides[deps.get_audit_log_query_service] = lambda: service

    try:
        response = client.get(
            f"/api/v1/organizations/{org_b}/audit-logs",
            headers=_invitation_test_headers(org_a),
        )
    finally:
        app.dependency_overrides.pop(deps.get_permission_evaluator, None)
        app.dependency_overrides.pop(deps.get_audit_log_query_service, None)

    assert response.status_code == 403
    assert service.calls == []


def test_audit_log_route_allows_authorized_same_tenant_query() -> None:
    org_id = new_uuid7()
    service = _AuditLogQueryServiceSpy()
    app.dependency_overrides[deps.get_permission_evaluator] = lambda: _AllowAllPermissions()
    app.dependency_overrides[deps.get_audit_log_query_service] = lambda: service

    try:
        response = client.get(
            f"/api/v1/organizations/{org_id}/audit-logs",
            headers=_invitation_test_headers(org_id),
        )
    finally:
        app.dependency_overrides.pop(deps.get_permission_evaluator, None)
        app.dependency_overrides.pop(deps.get_audit_log_query_service, None)

    assert response.status_code == 200
    assert response.json() == {"data": []}
    assert service.calls == [
        {"org_id": org_id, "category": None, "source": None, "limit": 50}
    ]


_ORG_ID = "00000000-0000-0000-0000-000000000000"
_USER_ID = "00000000-0000-0000-0000-000000000001"


def test_list_roles_without_authorization_header_is_rejected() -> None:
    """Regression test: list_roles previously had no authentication
    dependency (and no permission gate — 'role:read' didn't even exist in
    the catalog) at all, so any org's custom role names and permission
    grants were readable by anyone, unauthenticated."""
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/roles")
    assert response.status_code == 401


def test_permission_catalog_without_authorization_header_is_rejected() -> None:
    response = client.get("/api/v1/permissions")
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
