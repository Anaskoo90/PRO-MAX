from __future__ import annotations

import httpx
import pytest

from discord_bot.services.api_client import ApiClient


def _client(handler, *, bot_service_secret: str = "the-secret") -> ApiClient:
    return ApiClient(
        base_url="http://backend.test", bot_service_secret=bot_service_secret,
        transport=httpx.MockTransport(handler),
    )


async def test_complete_discord_setup_returns_ok_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/setup/complete"
        assert request.headers["X-GuildDesk-Bot-Secret"] == "the-secret"
        return httpx.Response(201, json={"data": {"id": "1", "status": "active"}})

    result = await _client(handler).complete_discord_setup(
        code="ABCD1234", discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    assert result.ok is True
    assert result.error_message is None


async def test_complete_discord_setup_surfaces_backend_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "invalid_setup_code", "message": "This setup code is invalid"})

    result = await _client(handler).complete_discord_setup(
        code="wrong", discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    assert result.ok is False
    assert result.error_message == "This setup code is invalid"


async def test_complete_discord_setup_handles_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = await _client(handler).complete_discord_setup(
        code="ABCD1234", discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    assert result.ok is False
    assert result.error_message == "Could not reach the GuildDesk API"


async def test_complete_discord_setup_falls_back_to_generic_message_for_unparseable_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>gateway error</html>")

    result = await _client(handler).complete_discord_setup(
        code="ABCD1234", discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )

    assert result.ok is False
    assert result.error_message == "Request failed"


async def test_get_guild_status_reports_linked_guild() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/guilds/111/status"
        return httpx.Response(
            200, json={"data": {"linked": True, "org_name": "Acme Corp", "discord_guild_name": "Acme HQ"}}
        )

    result = await _client(handler).get_guild_status(discord_guild_id="111")

    assert result.ok is True
    assert result.linked is True
    assert result.org_name == "Acme Corp"


async def test_get_guild_status_reports_unlinked_guild() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"linked": False}})

    result = await _client(handler).get_guild_status(discord_guild_id="999")

    assert result.ok is True
    assert result.linked is False
    assert result.org_name is None


async def test_get_guild_status_handles_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "unauthorized", "message": "Missing or invalid bot service secret"})

    result = await _client(handler).get_guild_status(discord_guild_id="111")

    assert result.ok is False
    assert result.error_message == "Missing or invalid bot service secret"


async def test_unlink_guild_returns_ok_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/discord/guilds/111/unlink"
        assert request.method == "POST"
        return httpx.Response(204)

    result = await _client(handler).unlink_guild(discord_guild_id="111", discord_user_id="999")

    assert result.ok is True


async def test_unlink_guild_surfaces_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "guild_not_linked", "message": "Discord guild '111' is not linked to any organization"})

    result = await _client(handler).unlink_guild(discord_guild_id="111", discord_user_id="999")

    assert result.ok is False
    assert "not linked" in result.error_message


async def test_check_health_reports_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"checks": [{"name": "database", "status": "healthy"}]})

    healthy = await _client(handler).check_health()
    assert healthy is True


async def test_check_health_reports_unhealthy_on_degraded_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"checks": [{"name": "database", "status": "unhealthy"}]})

    healthy = await _client(handler).check_health()
    assert healthy is False
