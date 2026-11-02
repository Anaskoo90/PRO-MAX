"""End-to-end (real Postgres) tests for organization suspension/deactivation.

Suspending an organization must (1) revoke every session its members hold,
(2) stop new logins, refreshes and existing access tokens, and (3) leave other
organizations alone. Reactivation lets users log in again but does not revive
old sessions.
"""

from __future__ import annotations

import uuid

import pytest
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.exceptions import OrganizationNotActiveError, SessionNotFoundError
from app.platform_core.errors.api_exceptions import UnauthorizedError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from sqlalchemy import text

from tests.identity.integration.test_login_flow import (
    _PASSWORD,
    _authenticate_access_token,
    _make_org_and_active_user,
    _make_service,
)

pytestmark = pytest.mark.asyncio


def _orgs(uow) -> OrganizationManagementService:
    return OrganizationManagementService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(), dispatcher=EventDispatcher()
    )


async def _tenant(uow, tag: str):
    email = f"{tag}-{uuid.uuid4().hex[:8]}@example.com"
    org, user = await _make_org_and_active_user(uow, slug=f"{tag}-{uuid.uuid4().hex[:8]}", email=email)
    return org, user, email


async def _login(uow, org, email):
    return (
        await _make_service(uow).login(
            org_id=OrgId(org.id), email=email, password=_PASSWORD,
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )
    ).tokens


async def _active_session_count(uow, org) -> int:
    return (
        await uow.session.execute(
            text(
                "SELECT count(*) FROM identity.sessions s JOIN identity.users u ON u.id = s.user_id "
                "WHERE u.org_id = :org AND s.revoked_at IS NULL"
            ),
            {"org": org.id},
        )
    ).scalar_one()


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_suspending_an_organization_ends_every_authentication_path(uow, operation: str) -> None:
    org, user, email = await _tenant(uow, "victim")
    service = _make_service(uow)
    tokens = await _login(uow, org, email)
    await _authenticate_access_token(service, tokens.access_token)  # works beforehand
    assert await _active_session_count(uow, org) == 1

    await getattr(_orgs(uow), operation)(org_id=org.id, actor_user_id=UserId(new_uuid7()))

    assert await _active_session_count(uow, org) == 0  # sessions revoked in the database
    with pytest.raises(UnauthorizedError):  # existing access token
        await _authenticate_access_token(service, tokens.access_token)
    with pytest.raises(SessionNotFoundError):  # refresh token of the revoked session
        await service.refresh(raw_refresh_token=tokens.refresh_token)
    with pytest.raises(OrganizationNotActiveError):  # a brand-new login
        await _login(uow, org, email)


async def test_suspending_one_organization_does_not_touch_another(uow) -> None:
    org_a, _user_a, email_a = await _tenant(uow, "a")
    org_b, _user_b, email_b = await _tenant(uow, "b")
    service = _make_service(uow)
    tokens_b = await _login(uow, org_b, email_b)
    await _login(uow, org_a, email_a)

    await _orgs(uow).suspend(org_id=org_a.id, actor_user_id=UserId(new_uuid7()))

    assert await _active_session_count(uow, org_a) == 0
    assert await _active_session_count(uow, org_b) == 1
    await _authenticate_access_token(service, tokens_b.access_token)  # still valid
    await service.refresh(raw_refresh_token=tokens_b.refresh_token)  # still refreshes


async def test_reactivation_permits_new_logins_but_not_old_sessions(uow) -> None:
    org, _user, email = await _tenant(uow, "back")
    service = _make_service(uow)
    old = await _login(uow, org, email)
    management = _orgs(uow)
    await management.suspend(org_id=org.id, actor_user_id=UserId(new_uuid7()))
    await management.reactivate(org_id=org.id, actor_user_id=UserId(new_uuid7()))

    with pytest.raises(UnauthorizedError):
        await _authenticate_access_token(service, old.access_token)
    with pytest.raises(SessionNotFoundError):
        await service.refresh(raw_refresh_token=old.refresh_token)
    fresh = await _login(uow, org, email)  # a new login is fine again
    await _authenticate_access_token(service, fresh.access_token)


async def test_every_session_of_every_member_is_revoked_in_one_pass(uow) -> None:
    org, _user, email = await _tenant(uow, "many")
    for _ in range(3):  # several devices for the same member
        await _login(uow, org, email)
    assert await _active_session_count(uow, org) == 3

    await _orgs(uow).suspend(org_id=org.id, actor_user_id=UserId(new_uuid7()))

    assert await _active_session_count(uow, org) == 0
