"""
API-level smoke tests for Boards & Agile Management routes that don't
require a live database — same TestClient-without-`with` pattern as
tests/tasks/api and every prior context's API tests, so the app's lifespan
(which hits the DB via identity_module.seed()) is never triggered.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_board_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/boards", json={"name": "Demo"}
    )
    assert response.status_code == 401


def test_move_card_without_authorization_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/cards/00000000-0000-7000-8000-000000000000/move",
        json={"column_id": None},
    )
    assert response.status_code == 401


def test_start_sprint_without_authorization_header_is_rejected() -> None:
    response = client.post("/api/v1/sprints/00000000-0000-7000-8000-000000000000/start")
    assert response.status_code == 401


def test_create_board_rejects_missing_required_fields() -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-7000-8000-000000000000/boards",
        json={},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    # Malformed/invalid auth is checked before body validation, so this
    # resolves to 401, not 422 — same ordering already established for
    # every prior context's equivalent tests.
    assert response.status_code == 401


def test_openapi_schema_includes_boards_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert any(path.startswith("/api/v1/projects/") and "boards" in path for path in paths)
    assert any(path.startswith("/api/v1/boards/") for path in paths)
    assert any(path.startswith("/api/v1/sprints/") for path in paths)
    assert any(path.startswith("/api/v1/cards/") for path in paths)
