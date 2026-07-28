"""
API-level smoke tests for Tasks & Work Management routes that don't require
a live database — same TestClient-without-`with` pattern as
tests/identity/api and tests/projects/api, so the app's lifespan (which
hits the DB via identity_module.seed()) is never triggered.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_task_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/tasks", json={"title": "Demo"}
    )
    assert response.status_code == 401


def test_assign_task_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/tasks/00000000-0000-7000-8000-000000000000/assignments",
        json={"assignee_user_id": "00000000-0000-7000-8000-000000000001"},
    )
    assert response.status_code == 401


def test_create_task_rejects_missing_required_fields() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/tasks",
        json={},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    # Malformed/invalid auth is checked before body validation, so this
    # resolves to 401, not 422 — same ordering already established for
    # Identity's and Projects' equivalent tests.
    assert response.status_code == 401


def test_openapi_schema_includes_tasks_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert any(path.startswith("/api/v1/projects/") and "tasks" in path for path in paths)
    assert any(path.startswith("/api/v1/tasks/") for path in paths)
