from __future__ import annotations

from dataclasses import dataclass

import pytest
from app.identity.application.authentication import OAuth2LoginService
from app.identity.application.dtos import AuthTokens, LoginResult
from app.identity.domain.entities import User
from app.identity.domain.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    OAuthProviderNotConfiguredError,
)
from app.identity.domain.value_objects import Email
from app.platform_core.messaging.idempotency import InMemoryIdempotencyStore
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeUnitOfWork

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class _ExternalIdentity:
    provider_key: str = "discord"
    subject: str = "provider-user-123"
    email: str | None = "member@example.com"
    email_verified: bool = True
    display_name: str | None = "Member"


class _OAuthClient:
    def __init__(self, identity: _ExternalIdentity | None = None) -> None:
        self.identity = identity or _ExternalIdentity()
        self.received_state: str | None = None
        self.exchange_count = 0

    def build_authorization_url(self, *, state: str) -> str:
        self.received_state = state
        return f"https://provider.example/authorize?state={state}"

    async def exchange_code(self, code: str) -> dict[str, str]:
        self.exchange_count += 1
        return {"access_token": f"token-for-{code}"}

    async def fetch_external_identity(self, token_response: dict[str, str]) -> _ExternalIdentity:
        return self.identity


class _AuthenticationService:
    def __init__(self, result: LoginResult | None = None) -> None:
        self.result = result or LoginResult(
            tokens=AuthTokens(access_token="access", refresh_token="refresh")
        )
        self.user_id = None

    async def login_external(self, *, user_id, ip_address: str, device_info: dict | None):
        self.user_id = user_id
        return self.result


def _service(
    uow: FakeUnitOfWork,
    *,
    client: _OAuthClient | None = None,
    auth: _AuthenticationService | None = None,
) -> tuple[OAuth2LoginService, _OAuthClient, _AuthenticationService]:
    oauth_client = client or _OAuthClient()
    auth_service = auth or _AuthenticationService()
    return (
        OAuth2LoginService(
            uow_factory=lambda: uow,
            oauth2_clients={"discord": oauth_client},
            authentication_service=auth_service,
            token_service=JwtTokenService(signing_key="a" * 32),
            state_replay_store=InMemoryIdempotencyStore(),
        ),
        oauth_client,
        auth_service,
    )


async def _existing_user(uow: FakeUnitOfWork, org_id: OrgId) -> User:
    user = User.register(
        org_id=org_id,
        email=Email("member@example.com"),
        password_hash="hash",
        display_name="Member",
    )
    user.verify_email()
    await uow.users.add(user)
    return user


async def test_authorization_state_is_signed_and_bound_to_provider_and_org() -> None:
    service, client, _ = _service(FakeUnitOfWork())
    org_id = OrgId(new_uuid7())

    url, state = service.build_authorization_url(provider_key="discord", org_id=org_id)

    assert client.received_state == state
    assert state in url
    claims = JwtTokenService(signing_key="a" * 32).verify_oauth_state_token(state)
    assert claims.org_id == org_id
    assert claims.provider_key == "discord"


async def test_callback_authenticates_existing_member_and_state_is_single_use() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    user = await _existing_user(uow, org_id)
    service, client, auth = _service(uow)
    _, state = service.build_authorization_url(provider_key="discord", org_id=org_id)

    result = await service.login_with_callback(
        provider_key="discord",
        code="valid-code",
        state=state,
        ip_address="203.0.113.4",
        device_info=None,
    )

    assert result.tokens is not None
    assert auth.user_id == user.id
    with pytest.raises(InvalidTokenError):
        await service.login_with_callback(
            provider_key="discord",
            code="valid-code",
            state=state,
            ip_address="203.0.113.4",
            device_info=None,
        )
    assert client.exchange_count == 1


async def test_callback_preserves_local_mfa_challenge_result() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    await _existing_user(uow, org_id)
    expected = LoginResult(
        mfa_challenge_token="signed-mfa-challenge",
        mfa_available_factors=("totp",),
    )
    service, _, _ = _service(uow, auth=_AuthenticationService(expected))
    _, state = service.build_authorization_url(provider_key="discord", org_id=org_id)

    result = await service.login_with_callback(
        provider_key="discord",
        code="valid-code",
        state=state,
        ip_address="203.0.113.4",
        device_info=None,
    )

    assert result == expected


@pytest.mark.parametrize(
    "identity",
    [
        _ExternalIdentity(email_verified=False),
        _ExternalIdentity(email=None, email_verified=False),
    ],
)
async def test_callback_rejects_identity_without_verified_email(
    identity: _ExternalIdentity,
) -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    service, _, _ = _service(uow, client=_OAuthClient(identity))
    _, state = service.build_authorization_url(provider_key="discord", org_id=org_id)

    with pytest.raises(InvalidCredentialsError):
        await service.login_with_callback(
            provider_key="discord",
            code="code",
            state=state,
            ip_address="127.0.0.1",
            device_info=None,
        )


async def test_callback_cannot_provision_uninvited_organization_member() -> None:
    uow = FakeUnitOfWork()
    service, _, _ = _service(uow)
    _, state = service.build_authorization_url(
        provider_key="discord", org_id=OrgId(new_uuid7())
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login_with_callback(
            provider_key="discord",
            code="code",
            state=state,
            ip_address="127.0.0.1",
            device_info=None,
        )
    assert uow.users.users == {}


async def test_callback_rejects_state_issued_for_another_provider() -> None:
    service, _, _ = _service(FakeUnitOfWork())
    state = JwtTokenService(signing_key="a" * 32).issue_oauth_state_token(
        provider_key="google", org_id=OrgId(new_uuid7())
    )

    with pytest.raises(InvalidTokenError):
        await service.login_with_callback(
            provider_key="discord",
            code="code",
            state=state,
            ip_address="127.0.0.1",
            device_info=None,
        )


async def test_unknown_provider_returns_controlled_not_found_error() -> None:
    service, _, _ = _service(FakeUnitOfWork())

    with pytest.raises(OAuthProviderNotConfiguredError):
        service.build_authorization_url(
            provider_key="unknown", org_id=OrgId(new_uuid7())
        )
