"""
API-level smoke tests for Discord Integration routes that don't require a
live database — same TestClient-without-`with` pattern as every prior
context's API tests, so the app's lifespan (which hits the DB via
identity_module.seed()) is never triggered.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_ORG_ID = "00000000-0000-7000-8000-000000000000"
_GUILD_LINK_ID = "00000000-0000-7000-8000-000000000001"


def test_request_setup_token_without_authorization_header_is_rejected() -> None:
    response = client.post(f"/api/v1/organizations/{_ORG_ID}/discord/setup-token")
    assert response.status_code == 401


def test_list_guild_links_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/discord/guild-links")
    assert response.status_code == 401


def test_unlink_guild_without_authorization_header_is_rejected() -> None:
    response = client.delete(f"/api/v1/organizations/{_ORG_ID}/discord/guild-links/{_GUILD_LINK_ID}")
    assert response.status_code == 401


def test_request_setup_token_with_garbage_bearer_token_is_rejected() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/discord/setup-token", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401


def test_complete_setup_without_bot_secret_header_is_rejected() -> None:
    response = client.post(
        "/api/v1/discord/setup/complete",
        json={"code": "ABCD1234", "discord_guild_id": "1", "discord_guild_name": "Acme", "discord_user_id": "2"},
    )
    assert response.status_code == 401


def test_complete_setup_with_wrong_bot_secret_is_rejected() -> None:
    response = client.post(
        "/api/v1/discord/setup/complete",
        json={"code": "ABCD1234", "discord_guild_id": "1", "discord_guild_name": "Acme", "discord_user_id": "2"},
        headers={"X-GuildDesk-Bot-Secret": "definitely-wrong"},
    )
    assert response.status_code == 401


def test_get_guild_status_without_bot_secret_header_is_rejected() -> None:
    response = client.get("/api/v1/discord/guilds/123/status")
    assert response.status_code == 401


def test_unlink_guild_by_discord_id_without_bot_secret_header_is_rejected() -> None:
    response = client.post("/api/v1/discord/guilds/123/unlink", json={"discord_user_id": "999"})
    assert response.status_code == 401


def test_bot_route_auth_is_checked_before_body_validation() -> None:
    # Missing bot secret AND an empty/invalid body — must still resolve to
    # 401, not 422, same ordering already established for every prior
    # context's equivalent tests.
    response = client.post("/api/v1/discord/setup/complete", json={})
    assert response.status_code == 401


def test_openapi_schema_includes_discord_integration_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/organizations/{org_id}/discord/setup-token" in paths
    assert "/api/v1/organizations/{org_id}/discord/guild-links" in paths
    assert "/api/v1/discord/setup/complete" in paths
    assert "/api/v1/discord/guilds/{discord_guild_id}/status" in paths
    assert "/api/v1/discord/guilds/{discord_guild_id}/unlink" in paths
