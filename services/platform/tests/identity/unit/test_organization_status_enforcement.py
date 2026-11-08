"""Regression tests: a suspended/deactivated organization cannot authenticate.

Before this fix `OrganizationManagementService.suspend` only flipped a status
flag: members of a suspended organization could still log in, refresh tokens
and use existing access tokens. Now every authentication path checks the
organization, and suspension/deactivation revokes the organization's sessions.
"""

from __future__ import annotations

import pytest
from app.identity.application.authentication import AuthenticationService, AuthPolicy
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.entities import Session, User
from app.identity.domain.exceptions import (
    InvalidCredentialsError,
    OrganizationNotActiveError,
    SessionNotFoundError,
)
from app.identity.domain.organization import Organization, OrganizationStatus
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio

_PASSWORD = "correct horse battery staple"
_POLICY = AuthPolicy()
_NOT_ACTIVE = [OrganizationStatus.SUSPENDED, OrganizationStatus.DEACTIVATED]


def _auth(uow: FakeUnitOfWork) -> AuthenticationService:
    return AuthenticationService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(),
        token_service=JwtTokenService(signing_key="a" * 32), dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()), policy=_POLICY,
    )


def _orgs(uow: FakeUnitOfWork) -> OrganizationManagementService:
    return OrganizationManagementService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(), dispatcher=EventDispatcher()
    )


async def _org(uow: FakeUnitOfWork, *, slug: str = "acme") -> Organization:
    org = Organization.create(name="Acme", slug=slug, owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    return org


async def _user(uow: FakeUnitOfWork, org: Organization, *, email: str = "user@example.com") -> User:
    user = User.register(
        org_id=OrgId(org.id), email=Email(email), password_hash=PasswordHashingService().hash(_PASSWORD),
        display_name="User",
    )
    user.verify_email()
    await uow.users.add(user)
    return user


async def _session(uow: FakeUnitOfWork, user: User, raw: str) -> Session:
    session = Session.create(
        user_id=user.id, refresh_token_hash=hash_for_lookup(raw, secret_pepper=_POLICY.refresh_token_pepper),
        device_info=None, ip_address="127.0.0.1", remember_me=True,
    )
    await uow.sessions.add(session)
    return session


def _set_status(org: Organization, status: OrganizationStatus) -> None:
    {OrganizationStatus.SUSPENDED: org.suspend, OrganizationStatus.DEACTIVATED: org.deactivate}[status]()


# ---- the three authentication paths -------------------------------------------------


@pytest.mark.parametrize("status", _NOT_ACTIVE)
async def test_login_is_refused_for_a_suspended_or_deactivated_organization(status) -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    _set_status(org, status)

    with pytest.raises(OrganizationNotActiveError):
        await _auth(uow).login(
            org_id=OrgId(org.id), email="user@example.com", password=_PASSWORD,
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )

    assert uow.sessions.sessions == {}  # no session was issued
    assert await uow.users.get_by_id(user.id) is not None


async def test_organization_status_is_not_disclosed_to_someone_without_the_password() -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    await _user(uow, org)
    org.suspend()

    with pytest.raises(InvalidCredentialsError):  # not OrganizationNotActiveError
        await _auth(uow).login(
            org_id=OrgId(org.id), email="user@example.com", password="wrong password",
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )


@pytest.mark.parametrize("status", _NOT_ACTIVE)
async def test_refresh_is_refused_for_a_suspended_or_deactivated_organization(status) -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    session = await _session(uow, user, "raw-refresh-token")
    _set_status(org, status)  # status changed by a path that did not revoke sessions

    with pytest.raises(OrganizationNotActiveError):
        await _auth(uow).refresh(raw_refresh_token="raw-refresh-token")

    assert session.is_active() and len(uow.sessions.sessions) == 1  # rejected before any rotation


@pytest.mark.parametrize("status", _NOT_ACTIVE)
async def test_existing_access_tokens_are_rejected_for_a_suspended_or_deactivated_organization(status) -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    session = await _session(uow, user, "raw")
    service = _auth(uow)
    assert await service.is_access_session_active(session_id=session.id, user_id=user.id) is True  # control

    _set_status(org, status)

    assert await service.is_access_session_active(session_id=session.id, user_id=user.id) is False


async def test_a_missing_organization_fails_closed() -> None:
    uow = FakeUnitOfWork()
    org = Organization.create(name="Ghost", slug="ghost", owner_user_id=UserId(new_uuid7()))  # never added
    user = await _user(uow, org)
    session = await _session(uow, user, "raw")

    assert await _auth(uow).is_access_session_active(session_id=session.id, user_id=user.id) is False
    with pytest.raises(OrganizationNotActiveError):
        await _auth(uow).refresh(raw_refresh_token="raw")


async def test_mfa_completion_is_refused_for_a_suspended_organization() -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    org.suspend()

    with pytest.raises(OrganizationNotActiveError):
        await _auth(uow).complete_mfa_challenge(
            user_id=user.id, ip_address="127.0.0.1", device_info=None, remember_me=False
        )

    assert uow.sessions.sessions == {}


async def test_external_oauth_login_is_refused_for_a_suspended_organization() -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    org.suspend()

    with pytest.raises(OrganizationNotActiveError):
        await _auth(uow).login_external(user_id=user.id, ip_address="127.0.0.1", device_info=None)

    assert uow.sessions.sessions == {}


async def test_active_organizations_are_unaffected() -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    await _session(uow, user, "raw-refresh-token")
    service = _auth(uow)

    logged_in = await service.login(
        org_id=OrgId(org.id), email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )
    refreshed = await service.refresh(raw_refresh_token="raw-refresh-token")

    assert logged_in.tokens is not None and refreshed.access_token


# ---- suspension revokes sessions ------------------------------------------------------


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_suspending_or_deactivating_an_organization_revokes_all_of_its_sessions(operation: str) -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    other_org = await _org(uow, slug="other")
    first = await _user(uow, org, email="a@example.com")
    second = await _user(uow, org, email="b@example.com")
    outsider = await _user(uow, other_org, email="c@example.com")
    mine = [await _session(uow, first, "a1"), await _session(uow, first, "a2"), await _session(uow, second, "b1")]
    theirs = await _session(uow, outsider, "c1")

    await getattr(_orgs(uow), operation)(org_id=org.id, actor_user_id=new_uuid7())

    assert all(not s.is_active() for s in mine)
    assert theirs.is_active()  # another tenant's session is untouched
    assert uow.audit_logs.records[-1].metadata == {"revoked_sessions": 3}
    with pytest.raises(SessionNotFoundError):  # the revoked refresh token is dead
        await _auth(uow).refresh(raw_refresh_token="a1")


async def test_reactivation_allows_fresh_logins_but_does_not_resurrect_old_sessions() -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    old = await _session(uow, user, "old-refresh-token")
    service = _orgs(uow)
    await service.suspend(org_id=org.id, actor_user_id=new_uuid7())
    await service.reactivate(org_id=org.id, actor_user_id=new_uuid7())

    assert not old.is_active()
    assert uow.audit_logs.records[-1].metadata == {}  # reactivation revokes nothing
    result = await _auth(uow).login(
        org_id=OrgId(org.id), email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )
    assert result.tokens is not None


# ---- lock discipline ------------------------------------------------------------------


async def test_status_changes_lock_the_organization_for_update_and_logins_lock_it_shared() -> None:
    uow = FakeUnitOfWork()
    org = await _org(uow)
    user = await _user(uow, org)
    session = await _session(uow, user, "raw-refresh-token")
    service = _auth(uow)

    await service.login(
        org_id=OrgId(org.id), email="user@example.com", password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )
    await service.refresh(raw_refresh_token="raw-refresh-token")
    assert uow.organizations.shared_org_ids == [org.id, org.id]  # login + refresh
    assert uow.organizations.locked_org_ids == []

    await service.is_access_session_active(session_id=session.id, user_id=user.id)
    assert uow.organizations.shared_org_ids == [org.id, org.id]  # per-request validation takes no lock

    await _orgs(uow).suspend(org_id=org.id, actor_user_id=new_uuid7())
    assert uow.organizations.locked_org_ids == [org.id]
