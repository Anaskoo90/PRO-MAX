from __future__ import annotations

import httpx
import pytest

from discord_bot.services.api_client import ApiClient


def _client(handler, *, bot_service_secret: str = "the-secret") -> ApiClient:
    return ApiClient(
        base_url="http://backend.test", bot_service_secret=bot_service_secret,
        transport=httpx.MockTransport(handler),
    )


async def test_list_ticket_categories_returns_parsed_categories() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/guilds/111/ticket-categories"
        return httpx.Response(
            200,
            json={"data": [{"id": "1", "name": "Billing", "discord_category_channel_id": "222", "staff_discord_role_ids": ["role-1"]}]},
        )

    result = await _client(handler).list_ticket_categories(discord_guild_id="111")

    assert result.ok is True
    assert len(result.categories) == 1
    assert result.categories[0].name == "Billing"


async def test_list_ticket_categories_handles_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "unauthorized", "message": "Missing or invalid bot service secret"})

    result = await _client(handler).list_ticket_categories(discord_guild_id="111")

    assert result.ok is False
    assert result.categories == []


async def test_create_ticket_category_returns_the_created_category() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/guilds/111/ticket-categories"
        assert request.headers["X-GuildDesk-Bot-Secret"] == "the-secret"
        return httpx.Response(
            201, json={"data": {"id": "1", "name": "Billing", "discord_category_channel_id": "222", "staff_discord_role_ids": []}}
        )

    result = await _client(handler).create_ticket_category(
        discord_guild_id="111", name="Billing", discord_category_channel_id="222", staff_discord_role_ids=[],
    )

    assert result.ok is True
    assert result.category.name == "Billing"


async def test_create_ticket_returns_the_created_ticket() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/tickets"
        return httpx.Response(
            201,
            json={"data": {"id": "1", "ticket_number": 1, "discord_channel_id": "222", "title": "Help", "status": "open", "claimed_by_discord_user_id": None}},
        )

    result = await _client(handler).create_ticket(
        discord_guild_id="111", discord_channel_id="222", title="Help", opener_discord_user_id="333",
    )

    assert result.ok is True
    assert result.ticket.status == "open"


async def test_create_ticket_surfaces_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "guild_not_linked_for_tickets", "message": "Discord guild '111' is not linked to a GuildDesk organization"})

    result = await _client(handler).create_ticket(
        discord_guild_id="111", discord_channel_id="222", title="Help", opener_discord_user_id="333",
    )

    assert result.ok is False
    assert "not linked" in result.error_message


async def test_get_ticket_by_channel_returns_the_ticket() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/tickets/by-channel/222"
        return httpx.Response(
            200,
            json={"data": {"id": "1", "ticket_number": 1, "discord_channel_id": "222", "title": "Help", "status": "claimed", "claimed_by_discord_user_id": "777"}},
        )

    result = await _client(handler).get_ticket_by_channel(discord_channel_id="222")

    assert result.ok is True
    assert result.ticket.claimed_by_discord_user_id == "777"


async def test_claim_ticket_returns_ok_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/tickets/1/claim"
        return httpx.Response(
            200,
            json={"data": {"id": "1", "ticket_number": 1, "discord_channel_id": "222", "title": "Help", "status": "claimed", "claimed_by_discord_user_id": "777"}},
        )

    result = await _client(handler).claim_ticket(ticket_id="1", claimant_discord_user_id="777")

    assert result.ok is True
    assert result.ticket.status == "claimed"


async def test_unclaim_ticket_returns_ok_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/tickets/1/unclaim"
        return httpx.Response(
            200,
            json={"data": {"id": "1", "ticket_number": 1, "discord_channel_id": "222", "title": "Help", "status": "open", "claimed_by_discord_user_id": None}},
        )

    result = await _client(handler).unclaim_ticket(ticket_id="1")

    assert result.ok is True
    assert result.ticket.status == "open"


async def test_transfer_ticket_returns_ok_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/tickets/1/transfer"
        return httpx.Response(
            200,
            json={"data": {"id": "1", "ticket_number": 1, "discord_channel_id": "222", "title": "Help", "status": "claimed", "claimed_by_discord_user_id": "888"}},
        )

    result = await _client(handler).transfer_ticket(ticket_id="1", new_claimant_discord_user_id="888")

    assert result.ok is True
    assert result.ticket.claimed_by_discord_user_id == "888"


async def test_close_ticket_returns_ok_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/tickets/1/close"
        return httpx.Response(
            200,
            json={"data": {"id": "1", "ticket_number": 1, "discord_channel_id": "222", "title": "Help", "status": "closed", "claimed_by_discord_user_id": None}},
        )

    result = await _client(handler).close_ticket(ticket_id="1", closed_by_discord_user_id="999")

    assert result.ok is True
    assert result.ticket.status == "closed"


async def test_ticket_methods_handle_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = await _client(handler).unclaim_ticket(ticket_id="1")

    assert result.ok is False
    assert result.error_message == "Could not reach the GuildDesk API"
