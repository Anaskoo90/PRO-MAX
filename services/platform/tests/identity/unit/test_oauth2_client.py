from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.identity.infrastructure.oauth2_client import (
    OAuth2Client,
    OAuth2ExchangeError,
    OAuth2ProviderConfig,
)


def _config() -> OAuth2ProviderConfig:
    return OAuth2ProviderConfig(
        provider_key="discord",
        client_id="client-id",
        client_secret="client-secret",
        authorization_endpoint="https://discord.com/oauth2/authorize",
        token_endpoint="https://discord.com/api/oauth2/token",
        userinfo_endpoint="https://discord.com/api/users/@me",
        redirect_uri="https://app.example.com/oauth/callback",
        scopes=("identify", "email"),
    )


def test_authorization_url_uses_caller_supplied_state_and_required_parameters() -> None:
    url = OAuth2Client(_config()).build_authorization_url(state="signed-state")
    query = parse_qs(urlparse(url).query)

    assert query["state"] == ["signed-state"]
    assert query["client_id"] == ["client-id"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["identify email"]


class _Response:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "id": "discord-user-123",
            "email": "member@example.com",
            "verified": True,
            "username": "Member",
        }


class _HttpClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, url: str, *, headers: dict[str, str]) -> _Response:
        assert headers == {"Authorization": "Bearer provider-access-token"}
        return _Response()


@pytest.mark.asyncio
async def test_userinfo_maps_discord_verified_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _HttpClient())

    identity = await OAuth2Client(_config()).fetch_external_identity(
        {"access_token": "provider-access-token"}
    )

    assert identity.subject == "discord-user-123"
    assert identity.email == "member@example.com"
    assert identity.email_verified is True
    assert identity.display_name == "Member"


class _FailingHttpClient(_HttpClient):
    async def get(self, url: str, *, headers: dict[str, str]) -> _Response:
        raise httpx.ConnectError("provider unavailable")


@pytest.mark.asyncio
async def test_userinfo_transport_failure_is_mapped_to_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _FailingHttpClient())

    with pytest.raises(OAuth2ExchangeError):
        await OAuth2Client(_config()).fetch_external_identity(
            {"access_token": "provider-access-token"}
        )
