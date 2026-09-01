"""
API-level smoke tests for Ticket System routes that don't require a live
database — same TestClient-without-`with` pattern as every prior context's
API tests, so the app's lifespan (which hits the DB via
identity_module.seed()) is never triggered.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_ORG_ID = "00000000-0000-7000-8000-000000000000"
_TICKET_ID = "00000000-0000-7000-8000-000000000001"


def test_create_ticket_without_authorization_header_is_rejected() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets",
        json={"discord_guild_id": "1", "discord_channel_id": "2", "title": "Help"},
    )
    assert response.status_code == 401


def test_list_tickets_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/tickets")
    assert response.status_code == 401


def test_get_ticket_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}")
    assert response.status_code == 401


def test_close_ticket_without_authorization_header_is_rejected() -> None:
    response = client.post(f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/close", json={})
    assert response.status_code == 401


def test_create_ticket_with_garbage_bearer_token_is_rejected() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets",
        json={"discord_guild_id": "1", "discord_channel_id": "2", "title": "Help"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401


def test_create_ticket_rejects_missing_required_fields() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets", json={},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    # Malformed/invalid auth is checked before body validation, so this
    # resolves to 401, not 422 — same ordering already established for
    # every prior context's equivalent tests.
    assert response.status_code == 401


def test_claim_ticket_without_authorization_header_is_rejected() -> None:
    response = client.post(f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/claim", json={})
    assert response.status_code == 401


def test_unclaim_ticket_without_authorization_header_is_rejected() -> None:
    response = client.post(f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/unclaim")
    assert response.status_code == 401


def test_transfer_ticket_without_authorization_header_is_rejected() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/transfer",
        json={"new_claimant_discord_user_id": "999"},
    )
    assert response.status_code == 401


def test_create_ticket_category_without_authorization_header_is_rejected() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/ticket-categories",
        json={"discord_guild_id": "1", "name": "Billing", "discord_category_channel_id": "2"},
    )
    assert response.status_code == 401


def test_list_ticket_categories_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/ticket-categories", params={"discord_guild_id": "1"})
    assert response.status_code == 401


def test_get_ticket_by_channel_without_bot_secret_is_rejected() -> None:
    response = client.get("/api/v1/discord/tickets/by-channel/123")
    assert response.status_code == 401


def test_create_ticket_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.post(
        "/api/v1/discord/tickets",
        json={"discord_guild_id": "1", "discord_channel_id": "2", "title": "Help", "opener_discord_user_id": "3"},
    )
    assert response.status_code == 401


def test_create_ticket_via_bot_with_wrong_bot_secret_is_rejected() -> None:
    response = client.post(
        "/api/v1/discord/tickets",
        json={"discord_guild_id": "1", "discord_channel_id": "2", "title": "Help", "opener_discord_user_id": "3"},
        headers={"X-GuildDesk-Bot-Secret": "definitely-wrong"},
    )
    assert response.status_code == 401


def test_claim_ticket_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.post(
        f"/api/v1/discord/tickets/{_TICKET_ID}/claim", json={"claimant_discord_user_id": "999"},
    )
    assert response.status_code == 401


def test_unclaim_ticket_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.post(f"/api/v1/discord/tickets/{_TICKET_ID}/unclaim")
    assert response.status_code == 401


def test_transfer_ticket_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.post(
        f"/api/v1/discord/tickets/{_TICKET_ID}/transfer", json={"new_claimant_discord_user_id": "999"},
    )
    assert response.status_code == 401


def test_close_ticket_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.post(
        f"/api/v1/discord/tickets/{_TICKET_ID}/close", json={"closed_by_discord_user_id": "999"},
    )
    assert response.status_code == 401


def test_list_ticket_categories_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.get("/api/v1/discord/guilds/123/ticket-categories")
    assert response.status_code == 401


def test_create_ticket_category_via_bot_without_bot_secret_is_rejected() -> None:
    response = client.post(
        "/api/v1/discord/guilds/123/ticket-categories",
        json={"discord_guild_id": "123", "name": "Billing", "discord_category_channel_id": "456"},
    )
    assert response.status_code == 401


def test_bot_route_auth_is_checked_before_body_validation() -> None:
    response = client.post("/api/v1/discord/tickets", json={})
    assert response.status_code == 401


def test_openapi_schema_includes_ticket_system_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/organizations/{org_id}/tickets" in paths
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}" in paths
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}/close" in paths
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}/claim" in paths
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}/unclaim" in paths
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}/transfer" in paths
    assert "/api/v1/organizations/{org_id}/ticket-categories" in paths
    assert "/api/v1/discord/tickets" in paths
    assert "/api/v1/discord/tickets/by-channel/{discord_channel_id}" in paths
    assert "/api/v1/discord/guilds/{discord_guild_id}/ticket-categories" in paths
