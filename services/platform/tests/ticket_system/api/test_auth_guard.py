"""
API-level smoke tests for Ticket System routes that don't require a live
database — same TestClient-without-`with` pattern as every prior context's
API tests, so the app's lifespan (which hits the DB via
identity_module.seed()) is never triggered.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from app.main import app, identity_module
from app.platform_core.shared_kernel.dtos import PagedResult
from app.platform_core.shared_kernel.utils import new_uuid7
from app.ticket_system.presentation import deps
from fastapi.testclient import TestClient

from tests.api_session_stub import allow_active_test_sessions, issue_session_bound_test_token

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _active_test_sessions():
    with allow_active_test_sessions(app):
        yield

_ORG_ID = "00000000-0000-7000-8000-000000000000"
_TICKET_ID = "00000000-0000-7000-8000-000000000001"


def _headers(org_id) -> dict[str, str]:
    token = issue_session_bound_test_token(
        identity_module.token_service,
        user_id=new_uuid7(),
        org_id=org_id,
    )
    return {"Authorization": f"Bearer {token}"}


class _TicketServiceSpy:
    def __init__(self) -> None:
        self.calls = []

    async def search_for_org(self, **kwargs):
        self.calls.append(kwargs)
        return PagedResult(
            items=[],
            total=0,
            page=kwargs["page"],
            page_size=kwargs["page_size"],
        )


class _CategoryServiceSpy:
    def __init__(self) -> None:
        self.calls = []

    async def list_for_guild(self, **kwargs):
        self.calls.append(kwargs)
        return []


class _MessageServiceSpy:
    def __init__(self) -> None:
        self.calls = []

    async def list_messages(self, **kwargs):
        self.calls.append(kwargs)
        return PagedResult(
            items=[],
            total=0,
            page=kwargs["page"],
            page_size=kwargs["page_size"],
        )


def test_create_ticket_without_authorization_header_is_rejected() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets",
        json={"discord_guild_id": "1", "discord_channel_id": "2", "title": "Help"},
    )
    assert response.status_code == 401


def test_list_tickets_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/tickets")
    assert response.status_code == 401


def test_ticket_and_category_lists_reject_cross_tenant_path_ids() -> None:
    caller_org_id = new_uuid7()
    other_org_id = new_uuid7()
    ticket_service = _TicketServiceSpy()
    category_service = _CategoryServiceSpy()
    app.dependency_overrides[deps.get_ticket_lifecycle_service] = lambda: ticket_service
    app.dependency_overrides[deps.get_ticket_category_service] = lambda: category_service

    try:
        headers = _headers(caller_org_id)
        tickets = client.get(
            f"/api/v1/organizations/{other_org_id}/tickets", headers=headers
        )
        categories = client.get(
            f"/api/v1/organizations/{other_org_id}/ticket-categories",
            params={"discord_guild_id": "111"},
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(deps.get_ticket_lifecycle_service, None)
        app.dependency_overrides.pop(deps.get_ticket_category_service, None)

    assert (tickets.status_code, categories.status_code) == (403, 403)
    assert ticket_service.calls == []
    assert category_service.calls == []


def test_ticket_and_category_lists_allow_same_tenant_calls() -> None:
    org_id = new_uuid7()
    ticket_service = _TicketServiceSpy()
    category_service = _CategoryServiceSpy()
    app.dependency_overrides[deps.get_ticket_lifecycle_service] = lambda: ticket_service
    app.dependency_overrides[deps.get_ticket_category_service] = lambda: category_service

    try:
        headers = _headers(org_id)
        tickets = client.get(
            f"/api/v1/organizations/{org_id}/tickets", headers=headers
        )
        categories = client.get(
            f"/api/v1/organizations/{org_id}/ticket-categories",
            params={"discord_guild_id": "111"},
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(deps.get_ticket_lifecycle_service, None)
        app.dependency_overrides.pop(deps.get_ticket_category_service, None)

    assert (tickets.status_code, categories.status_code) == (200, 200)
    assert ticket_service.calls[0]["org_id"] == org_id
    assert category_service.calls[0]["org_id"] == org_id
    assert category_service.calls[0]["actor_user_id"] is not None


def test_get_ticket_without_authorization_header_is_rejected() -> None:
    response = client.get(f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}")
    assert response.status_code == 401


def test_ticket_messages_without_authorization_header_are_rejected() -> None:
    list_response = client.get(
        f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/messages"
    )
    create_response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/messages",
        json={"body": "Help"},
    )

    assert (list_response.status_code, create_response.status_code) == (401, 401)


def test_ticket_message_body_cannot_be_only_whitespace() -> None:
    response = client.post(
        f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/messages",
        json={"body": "   "},
        headers=_headers(UUID(_ORG_ID)),
    )

    assert response.status_code == 422


def test_ticket_attachment_routes_without_authorization_are_rejected() -> None:
    base = f"/api/v1/organizations/{_ORG_ID}/tickets/{_TICKET_ID}/attachments"
    attachment_id = "00000000-0000-7000-8000-000000000002"

    responses = (
        client.get(base),
        client.post(base, files={"file": ("proof.txt", b"proof", "text/plain")}),
        client.get(f"{base}/{attachment_id}/content"),
        client.delete(f"{base}/{attachment_id}"),
    )

    assert [response.status_code for response in responses] == [401, 401, 401, 401]


def test_ticket_message_list_enforces_path_tenant_before_calling_service() -> None:
    caller_org_id = new_uuid7()
    other_org_id = new_uuid7()
    service = _MessageServiceSpy()
    app.dependency_overrides[deps.get_ticket_message_service] = lambda: service

    try:
        denied = client.get(
            f"/api/v1/organizations/{other_org_id}/tickets/{_TICKET_ID}/messages",
            headers=_headers(caller_org_id),
        )
        allowed = client.get(
            f"/api/v1/organizations/{caller_org_id}/tickets/{_TICKET_ID}/messages",
            headers=_headers(caller_org_id),
        )
    finally:
        app.dependency_overrides.pop(deps.get_ticket_message_service, None)

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert len(service.calls) == 1
    assert service.calls[0]["org_id"] == caller_org_id


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


def test_ticket_message_bot_routes_without_bot_secret_are_rejected() -> None:
    list_response = client.get(f"/api/v1/discord/tickets/{_TICKET_ID}/messages")
    create_response = client.post(
        f"/api/v1/discord/tickets/{_TICKET_ID}/messages",
        json={
            "body": "Discord message",
            "author_discord_user_id": "1",
            "discord_message_id": "2",
        },
    )
    channel_create_response = client.post(
        "/api/v1/discord/tickets/by-channel/2/messages",
        json={
            "body": "Discord message",
            "author_discord_user_id": "1",
            "discord_message_id": "2",
        },
    )
    attachment_response = client.post(
        "/api/v1/discord/tickets/by-channel/2/attachments",
        data={
            "uploaded_by_discord_user_id": "1",
            "discord_attachment_id": "2",
        },
        files={"file": ("proof.txt", b"proof", "text/plain")},
    )

    assert (
        list_response.status_code,
        create_response.status_code,
        channel_create_response.status_code,
        attachment_response.status_code,
    ) == (401, 401, 401, 401)


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
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}/messages" in paths
    assert "/api/v1/organizations/{org_id}/tickets/{ticket_id}/attachments" in paths
    assert (
        "/api/v1/organizations/{org_id}/tickets/{ticket_id}/attachments/"
        "{attachment_id}/content"
    ) in paths
    assert "/api/v1/organizations/{org_id}/ticket-categories" in paths
    assert "/api/v1/discord/tickets" in paths
    assert "/api/v1/discord/tickets/by-channel/{discord_channel_id}" in paths
    assert "/api/v1/discord/tickets/{ticket_id}/messages" in paths
    assert "/api/v1/discord/tickets/by-channel/{discord_channel_id}/messages" in paths
    assert "/api/v1/discord/tickets/by-channel/{discord_channel_id}/attachments" in paths
    assert "/api/v1/discord/guilds/{discord_guild_id}/ticket-categories" in paths
