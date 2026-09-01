"""
API-level smoke tests for Projects & Workspaces routes that don't require a
live database — same TestClient-without-`with` pattern as
tests/identity/api/test_health_and_auth_guard.py, so the app's lifespan
(which hits the DB via identity_module.seed()) is never triggered.

Full authenticated create-workspace/create-project flows belong in
tests/projects/integration, since they need the whole stack running.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, identity_module
from app.platform_core.shared_kernel.utils import new_uuid7

client = TestClient(app)


def test_create_workspace_without_authorization_header_is_rejected() -> None:
    response = client.post("/api/v1/workspaces", json={"name": "Eng", "slug": "eng"})
    assert response.status_code == 401


def test_workspace_and_template_reads_without_authorization_header_are_rejected() -> None:
    org_id = "00000000-0000-7000-8000-000000000000"
    resource_id = "00000000-0000-7000-8000-000000000001"

    for path in (
        f"/api/v1/organizations/{org_id}/workspaces",
        f"/api/v1/workspaces/{resource_id}",
        f"/api/v1/workspaces/{resource_id}/members",
        f"/api/v1/organizations/{org_id}/project-templates",
        f"/api/v1/project-templates/{resource_id}/export",
    ):
        assert client.get(path).status_code == 401


def test_org_a_cannot_list_org_b_workspaces_or_templates() -> None:
    org_a = new_uuid7()
    org_b = new_uuid7()
    token = identity_module.token_service.issue_access_token(
        user_id=new_uuid7(), org_id=org_a, scopes=[]
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/v1/organizations/{org_b}/workspaces", headers=headers).status_code == 403
    assert client.get(f"/api/v1/organizations/{org_b}/project-templates", headers=headers).status_code == 403


def test_create_project_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/workspaces/00000000-0000-7000-8000-000000000000/projects", json={"name": "Demo"}
    )
    assert response.status_code == 401


def test_invite_project_member_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/members/invite",
        json={"email": "person@example.com", "role": "contributor"},
    )
    assert response.status_code == 401


def test_create_workspace_rejects_missing_required_fields() -> None:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "Eng"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    # Malformed auth is checked by the route dependency before body
    # validation runs, so this still resolves to 401, not 422 — asserting
    # that ordering explicitly since it's easy to get backwards.
    assert response.status_code == 401


def test_openapi_schema_includes_projects_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/workspaces" in paths
    assert any(path.startswith("/api/v1/projects/") for path in paths)
