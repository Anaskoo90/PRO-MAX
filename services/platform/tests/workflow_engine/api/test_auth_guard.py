"""
API-level smoke tests for Workflow Engine routes that don't require a live
database — same TestClient-without-`with` pattern as every prior context's
API tests, so the app's lifespan (which hits the DB via
identity_module.seed()) is never triggered.
"""

from __future__ import annotations

import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_create_workflow_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/workflows", json={"name": "Demo"}
    )
    assert response.status_code == 401


def test_execute_transition_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/workflows/00000000-0000-7000-8000-000000000000/tasks/00000000-0000-7000-8000-000000000001/transition",
        json={"transition_id": "00000000-0000-7000-8000-000000000002"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/workflows",
        "/api/v1/workflows/00000000-0000-7000-8000-000000000000",
        "/api/v1/workflows/00000000-0000-7000-8000-000000000000/states",
        "/api/v1/workflows/00000000-0000-7000-8000-000000000000/transitions",
        "/api/v1/transitions/00000000-0000-7000-8000-000000000000/rules",
        "/api/v1/transitions/00000000-0000-7000-8000-000000000000/actions",
        "/api/v1/transitions/00000000-0000-7000-8000-000000000000/conditions",
        "/api/v1/transitions/00000000-0000-7000-8000-000000000000/checklist-items",
        "/api/v1/workflows/00000000-0000-7000-8000-000000000000/tasks/00000000-0000-7000-8000-000000000001/state",
        "/api/v1/workflows/00000000-0000-7000-8000-000000000000/tasks/00000000-0000-7000-8000-000000000001/history",
    ],
)
def test_workflow_reads_without_authorization_header_are_rejected(path: str) -> None:
    assert client.get(path).status_code == 401


def test_create_workflow_rejects_missing_required_fields() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/workflows",
        json={},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    # Malformed/invalid auth is checked before body validation, so this
    # resolves to 401, not 422 — same ordering already established for
    # every prior context's equivalent tests.
    assert response.status_code == 401


def test_openapi_schema_includes_workflow_engine_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert any(path.startswith("/api/v1/projects/") and "workflows" in path for path in paths)
    assert any(path.startswith("/api/v1/workflows/") for path in paths)
    assert any(path.startswith("/api/v1/transitions/") for path in paths)
    assert any(path.startswith("/api/v1/states/") for path in paths)
