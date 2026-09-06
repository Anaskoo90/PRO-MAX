"""
Regression test for Bug #2: request_password_reset committed the reset
token, then let NoProviderRegisteredError escape uncaught when no email
provider is configured, turning an already-successful request into an
unhandled 500 — and, because that only happened for a *registered* email
(an unregistered one returns early before ever reaching the dispatch
call), it also leaked account existence via the response's success/error
split.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.identity.application.password_management import PasswordManagementService
from app.identity.domain.entities import User
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio

_PASSWORD = "Correct-Horse-Battery-9"


def _make_service(uow) -> PasswordManagementService:
    return PasswordManagementService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(),
        notification_dispatcher=NotificationDispatcher(),  # no providers registered — reproduces the bug condition
        dispatcher=EventDispatcher(),
    )


async def _make_org(uow) -> OrgId:
    # users.org_id is a real foreign key to organizations.id — a bare
    # OrgId(new_uuid7()) with no matching row would violate it.
    org = Organization.create(name="Acme", slug=f"acme-{new_uuid7().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.commit()
    return OrgId(org.id)


async def _register_user(uow, org_id: OrgId, email: str) -> User:
    user = User.register(
        org_id=org_id, email=Email(email), password_hash=PasswordHashingService().hash(_PASSWORD),
        display_name="Owner",
    )
    await uow.users.add(user)
    await uow.commit()
    return user


async def test_password_reset_for_a_registered_email_does_not_raise_with_no_provider_configured(uow) -> None:
    org_id = await _make_org(uow)
    email = f"owner-{new_uuid7().hex[:12]}@example.com"
    await _register_user(uow, org_id, email)
    service = _make_service(uow)

    # Must complete without raising — this is exactly what used to 500.
    await service.request_password_reset(org_id=org_id, email=email)


async def test_password_reset_token_is_created_and_usable_despite_no_notification_provider(uow) -> None:
    org_id = await _make_org(uow)
    email = f"owner-{new_uuid7().hex[:12]}@example.com"
    user = await _register_user(uow, org_id, email)
    service = _make_service(uow)

    known_raw_token = "known-raw-reset-token-for-this-test"
    with patch("secrets.token_urlsafe", return_value=known_raw_token):
        await service.request_password_reset(org_id=org_id, email=email)

    # The token must have actually been persisted (not skipped), and must
    # be the real, usable token — not just any row.
    token = await uow.password_reset_tokens.get_by_token_hash(
        hash_for_lookup(known_raw_token, secret_pepper="change-me-in-production")
    )
    assert token is not None
    assert token.user_id == user.id


async def test_password_reset_for_an_unregistered_email_behaves_identically_to_a_registered_one(uow) -> None:
    org_id = await _make_org(uow)
    service = _make_service(uow)

    # No user exists for this email at all. Before the fix, a registered
    # email would 500 while this path returned normally — an observable
    # difference an attacker could use to enumerate accounts. After the
    # fix, both simply complete without raising, so the two paths are
    # indistinguishable from the caller's point of view.
    await service.request_password_reset(org_id=org_id, email="nobody@example.com")
