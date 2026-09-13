"""
Regression test for Bug #1: register_organization_with_owner previously
constructed the owner via the raw User(...) constructor instead of
User.register(...), so UserRegistered was never recorded, the real
subscriber (EmailVerificationService.on_user_registered, wired exactly
this way in identity/composition.py) never ran, no verification token was
ever created, and a self-registered owner could never verify their email
or log in. This wires the same subscription production uses and proves
the whole chain end-to-end against a real database.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.identity.application.authentication import AuthenticationService
from app.identity.application.email_verification import EmailVerificationService
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.events import UserRegistered
from app.identity.domain.exceptions import AccountNotActiveError
from app.identity.infrastructure.outbox import OutboxMessageOrmModel
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.notifications.email_provider import EmailMessage, EmailSendError
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.utils import new_uuid7
from sqlalchemy import select

from tests.identity.unit.fakes import FakeAuditRecordSink

pytestmark = pytest.mark.asyncio

_PASSWORD = "Correct-Horse-Battery-9"
_TOKEN_PEPPER = "test-token-pepper-with-at-least-32-characters"


class _UnavailableEmailProvider:
    async def send(self, message: EmailMessage) -> None:
        raise EmailSendError("smtp connection refused")


def _make_services(uow, notification_dispatcher: NotificationDispatcher | None = None):
    dispatcher = EventDispatcher()
    org_service = OrganizationManagementService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        dispatcher=dispatcher,
    )
    email_service = EmailVerificationService(
        uow_factory=lambda: uow,
        dispatcher=dispatcher,
        notification_dispatcher=notification_dispatcher or NotificationDispatcher(),
        token_pepper=_TOKEN_PEPPER,
        verification_link_base_url="https://app.test/verify",
    )
    auth_service = AuthenticationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        token_service=JwtTokenService(signing_key="a" * 32),
        dispatcher=dispatcher,
        audit_logger=AuditLogger(FakeAuditRecordSink()),
    )
    # Same subscription identity/composition.py wires in production — this
    # is what was silently never triggered before the fix.
    dispatcher.subscribe(UserRegistered, email_service.on_user_registered)
    return org_service, auth_service


async def test_registration_succeeds_and_persists_verification_token_during_email_outage(
    uow,
) -> None:
    org_service, _ = _make_services(
        uow,
        NotificationDispatcher(email_provider=_UnavailableEmailProvider()),
    )
    known_raw_token = "known-token-created-during-mail-outage"

    with patch("secrets.token_urlsafe", return_value=known_raw_token):
        _, owner_id = await org_service.register_organization_with_owner(
            org_name="Outage Org",
            slug=f"outage-{new_uuid7().hex[:12]}",
            owner_email=f"owner-{new_uuid7().hex[:12]}@example.com",
            owner_password=_PASSWORD,
            owner_display_name="Owner",
        )

    token = await uow.email_verification_tokens.get_by_token_hash(
        hash_for_lookup(known_raw_token, secret_pepper=_TOKEN_PEPPER)
    )
    assert token is not None
    assert token.user_id == owner_id


async def test_self_registration_fires_user_registered_and_creates_a_usable_verification_token(
    uow,
) -> None:
    org_service, auth_service = _make_services(uow)
    slug = f"acme-{new_uuid7().hex[:12]}"
    email = f"owner-{new_uuid7().hex[:12]}@example.com"

    known_raw_token = "known-raw-token-for-this-test"
    with patch("secrets.token_urlsafe", return_value=known_raw_token):
        org_dto, owner_id = await org_service.register_organization_with_owner(
            org_name="Acme",
            slug=slug,
            owner_email=email,
            owner_password=_PASSWORD,
            owner_display_name="Owner",
        )

    # The org's owner_user_id must point at the real registered user, not a
    # discarded placeholder — this was the other half of the fix.
    persisted_org = await uow.organizations.get_by_id(org_dto.id)
    assert persisted_org.owner_user_id == owner_id

    # UserRegistered must have actually fired and been handled: a real,
    # usable verification token now exists.
    token = await uow.email_verification_tokens.get_by_token_hash(
        hash_for_lookup(known_raw_token, secret_pepper=_TOKEN_PEPPER)
    )
    assert token is not None
    assert token.user_id == owner_id

    # Login must be rejected before verification (unchanged, correct
    # behavior) ...
    with pytest.raises(AccountNotActiveError):
        await auth_service.login(
            org_id=org_dto.id,
            email=email,
            password=_PASSWORD,
            ip_address="127.0.0.1",
            device_info=None,
            remember_me=False,
        )

    # ... and the owner must be able to complete verification and then log
    # in — the actual end-to-end guarantee this bug broke.
    email_service = EmailVerificationService(
        uow_factory=lambda: uow,
        dispatcher=EventDispatcher(),
        notification_dispatcher=NotificationDispatcher(),
        token_pepper=_TOKEN_PEPPER,
        verification_link_base_url="https://app.test/verify",
    )
    await email_service.verify_email(raw_token=known_raw_token)

    login_result = await auth_service.login(
        org_id=org_dto.id,
        email=email,
        password=_PASSWORD,
        ip_address="127.0.0.1",
        device_info=None,
        remember_me=False,
    )
    assert login_result.tokens is not None

    rows = (
        await uow.session.execute(
            select(OutboxMessageOrmModel).where(
                OutboxMessageOrmModel.org_id == org_dto.id
            )
        )
    ).scalars().all()
    event_types = {
        row.payload["payload"]["event_type"]
        for row in rows
    }
    assert {
        "identity.organization_created",
        "identity.user_registered",
        "identity.user_email_verified",
        "identity.user_logged_in",
    }.issubset(event_types)
