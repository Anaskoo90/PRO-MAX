"""Regression tests for H1: suspending/deactivating an account must kill its
sessions, and refresh tokens must not work for a non-active account."""

from __future__ import annotations

import pytest
from app.identity.application.authentication import AuthenticationService, AuthPolicy
from app.identity.application.user_management import UserManagementService
from app.identity.domain.entities import Session, User, UserStatus
from app.identity.domain.exceptions import (
    AccountNotActiveError,
    OrganizationOwnerProtectedError,
    SessionNotFoundError,
)
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio

_POLICY = AuthPolicy()


def _management(uow: FakeUnitOfWork) -> UserManagementService:
    return UserManagementService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
        file_storage=object(),
    )


def _authentication(uow: FakeUnitOfWork) -> AuthenticationService:
    return AuthenticationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        token_service=JwtTokenService(signing_key="a" * 32),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
        policy=_POLICY,
    )


async def _add_org(uow: FakeUnitOfWork, *, owner_user_id: UserId) -> Organization:
    org = Organization.create(name="Acme", slug=f"acme-{new_uuid7().hex[:8]}", owner_user_id=owner_user_id)
    await uow.organizations.add(org)
    return org


async def _add_active_user(uow: FakeUnitOfWork, org_id: OrgId, *, email: str = "member@example.com") -> User:
    user = User.register(org_id=org_id, email=Email(email), password_hash="hash", display_name="Member")
    user.verify_email()
    await uow.users.add(user)
    return user


async def _add_session(uow: FakeUnitOfWork, user: User, *, raw_refresh_token: str) -> Session:
    session = Session.create(
        user_id=user.id,
        refresh_token_hash=hash_for_lookup(raw_refresh_token, secret_pepper=_POLICY.refresh_token_pepper),
        device_info=None,
        ip_address="127.0.0.1",
        remember_me=True,
    )
    await uow.sessions.add(session)
    return session


async def test_suspend_revokes_every_active_session_of_the_target_user_only() -> None:
    uow = FakeUnitOfWork()
    org = await _add_org(uow, owner_user_id=UserId(new_uuid7()))
    target = await _add_active_user(uow, OrgId(org.id))
    bystander = await _add_active_user(uow, OrgId(org.id), email="other@example.com")
    target_sessions = [await _add_session(uow, target, raw_refresh_token=f"t{i}") for i in range(2)]
    bystander_session = await _add_session(uow, bystander, raw_refresh_token="b0")

    await _management(uow).suspend(
        org_id=OrgId(org.id), user_id=target.id, reason="policy", actor_user_id=new_uuid7()
    )

    assert target.status == UserStatus.SUSPENDED
    assert all(not s.is_active() for s in target_sessions)
    assert bystander_session.is_active()


async def test_deactivate_account_revokes_every_active_session() -> None:
    uow = FakeUnitOfWork()
    org = await _add_org(uow, owner_user_id=UserId(new_uuid7()))
    user = await _add_active_user(uow, OrgId(org.id))
    sessions = [await _add_session(uow, user, raw_refresh_token=f"d{i}") for i in range(2)]

    await _management(uow).deactivate_account(user_id=user.id)

    assert user.status == UserStatus.DEACTIVATED
    assert all(not s.is_active() for s in sessions)


async def test_refresh_token_issued_before_suspension_no_longer_works() -> None:
    uow = FakeUnitOfWork()
    org = await _add_org(uow, owner_user_id=UserId(new_uuid7()))
    user = await _add_active_user(uow, OrgId(org.id))
    await _add_session(uow, user, raw_refresh_token="raw-refresh-token")
    await _management(uow).suspend(
        org_id=OrgId(org.id), user_id=user.id, reason="policy", actor_user_id=new_uuid7()
    )

    with pytest.raises(SessionNotFoundError):
        await _authentication(uow).refresh(raw_refresh_token="raw-refresh-token")

    # nothing new was minted for the suspended account
    assert [s for s in uow.sessions.sessions.values() if s.is_active()] == []


@pytest.mark.parametrize("status", ["suspended", "deactivated"])
async def test_refresh_rejects_a_non_active_account_even_if_its_session_survived(status: str) -> None:
    """Defense in depth: simulates a session that slipped past revocation
    (e.g. a status change made by another code path)."""
    uow = FakeUnitOfWork()
    org = await _add_org(uow, owner_user_id=UserId(new_uuid7()))
    user = await _add_active_user(uow, OrgId(org.id))
    session = await _add_session(uow, user, raw_refresh_token="raw-refresh-token")
    if status == "suspended":
        user.suspend(reason="policy")
    else:
        user.deactivate()
    await uow.users.update(user)

    with pytest.raises(AccountNotActiveError):
        await _authentication(uow).refresh(raw_refresh_token="raw-refresh-token")

    assert session.is_active()  # rejected before any rotation happened
    assert len(uow.sessions.sessions) == 1


async def test_refresh_still_works_for_an_active_account() -> None:
    uow = FakeUnitOfWork()
    org = await _add_org(uow, owner_user_id=UserId(new_uuid7()))
    user = await _add_active_user(uow, OrgId(org.id))
    await _add_session(uow, user, raw_refresh_token="raw-refresh-token")

    tokens = await _authentication(uow).refresh(raw_refresh_token="raw-refresh-token")

    assert tokens.access_token and tokens.refresh_token


async def test_the_designated_owner_cannot_be_suspended_and_keeps_their_sessions() -> None:
    uow = FakeUnitOfWork()
    owner_id = UserId(new_uuid7())
    org = await _add_org(uow, owner_user_id=owner_id)
    owner = User.register(
        org_id=OrgId(org.id), email=Email("owner@example.com"), password_hash="hash", display_name="Owner"
    )
    owner.id = owner_id
    owner.verify_email()
    await uow.users.add(owner)
    session = await _add_session(uow, owner, raw_refresh_token="owner-token")

    with pytest.raises(OrganizationOwnerProtectedError):
        await _management(uow).suspend(
            org_id=OrgId(org.id), user_id=owner.id, reason="x", actor_user_id=new_uuid7()
        )

    assert owner.status == UserStatus.ACTIVE
    assert session.is_active()


async def test_the_designated_owner_cannot_deactivate_their_own_account() -> None:
    uow = FakeUnitOfWork()
    owner_id = UserId(new_uuid7())
    org = await _add_org(uow, owner_user_id=owner_id)
    owner = User.register(
        org_id=OrgId(org.id), email=Email("owner@example.com"), password_hash="hash", display_name="Owner"
    )
    owner.id = owner_id
    owner.verify_email()
    await uow.users.add(owner)

    with pytest.raises(OrganizationOwnerProtectedError):
        await _management(uow).deactivate_account(user_id=owner.id)

    assert owner.status == UserStatus.ACTIVE
