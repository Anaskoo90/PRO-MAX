"""
Integration coverage for the login + refresh flow against a real database.

Login itself (org_id vs org_slug resolution, password verification) is
already covered at the unit level against FakeUnitOfWork
(tests/identity/unit/test_authentication_service.py) — these tests exist
to catch anything only a real SQLAlchemy repository + Alembic schema could
surface (mapper mistakes, unique constraints, session persistence), and to
cover refresh-token issuance/rotation end-to-end, which nothing else does.
"""

from __future__ import annotations

import uuid

import pytest

from app.identity.application.authentication import AuthenticationService
from app.identity.domain.entities import User
from app.identity.domain.exceptions import InvalidCredentialsError, SessionNotFoundError
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.identity.unit.fakes import FakeAuditRecordSink

pytestmark = pytest.mark.asyncio

_PASSWORD = "Correct-Horse-Battery-9"


def _make_service(uow) -> AuthenticationService:
    return AuthenticationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        token_service=JwtTokenService(signing_key="a" * 32),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
    )


async def _make_org_and_active_user(uow, *, slug: str, email: str) -> tuple[Organization, User]:
    org = Organization.create(name="Acme", slug=slug, owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    user = User.register(
        org_id=OrgId(org.id), email=Email(email), password_hash=PasswordHashingService().hash(_PASSWORD),
        display_name="A User",
    )
    user.verify_email()
    await uow.users.add(user)
    await uow.commit()
    return org, user


async def test_login_with_org_id_against_real_database(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, _user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    service = _make_service(uow)

    result = await service.login(
        org_id=OrgId(org.id), email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    assert result.tokens is not None
    assert result.mfa_challenge_user_id is None


async def test_login_with_org_slug_against_real_database(uow) -> None:
    slug = f"acme-{uuid.uuid4().hex[:12]}"
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, _user = await _make_org_and_active_user(uow, slug=slug, email=email)
    service = _make_service(uow)

    result = await service.login(
        org_slug=slug, email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    assert result.tokens is not None
    persisted_user = await uow.users.get_by_email(OrgId(org.id), email)
    assert persisted_user is not None
    assert persisted_user.org_id == org.id


async def test_login_with_wrong_password_is_rejected_against_real_database(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, _user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    service = _make_service(uow)

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            org_id=OrgId(org.id), email=email, password="wrong-password",
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )


async def test_refresh_token_issues_new_tokens_and_rotates_the_old_one(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, _user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    service = _make_service(uow)

    login_result = await service.login(
        org_id=OrgId(org.id), email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )
    assert login_result.tokens is not None
    original_refresh_token = login_result.tokens.refresh_token

    refreshed = await service.refresh(raw_refresh_token=original_refresh_token)

    # The access token JWT is deterministic given identical claims and a
    # same-second timestamp, so it may legitimately be identical to the
    # previous one — the meaningful rotation invariant is the refresh token
    # changing and the old one being revoked (checked below).
    assert refreshed.refresh_token != original_refresh_token

    # Rotation must actually revoke the old refresh token — a leaked token
    # that was already used should not still be usable.
    with pytest.raises(SessionNotFoundError):
        await service.refresh(raw_refresh_token=original_refresh_token)

    # The new refresh token, in contrast, must still be valid.
    refreshed_again = await service.refresh(raw_refresh_token=refreshed.refresh_token)
    assert refreshed_again.refresh_token != refreshed.refresh_token


async def test_logout_revokes_the_refresh_token_against_real_database(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, _user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    service = _make_service(uow)

    login_result = await service.login(
        org_id=OrgId(org.id), email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )
    assert login_result.tokens is not None

    await service.logout(raw_refresh_token=login_result.tokens.refresh_token)

    with pytest.raises(SessionNotFoundError):
        await service.refresh(raw_refresh_token=login_result.tokens.refresh_token)
