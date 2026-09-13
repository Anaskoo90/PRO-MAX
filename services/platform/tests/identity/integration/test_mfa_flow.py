"""
Integration coverage for the full MFA chain against a real database:
enroll a TOTP factor, confirm it, then prove that a subsequent login stops
at a challenge (never issues tokens directly) and that only a correct
code — not an arbitrary one — completes it via verify_mfa_challenge.

Nothing else in the suite exercises this chain end-to-end: the MFA unit
tests use fakes, and the plain login integration tests
(test_login_flow.py) intentionally use MFA-less users.
"""

from __future__ import annotations

import uuid

import pyotp
import pytest
from app.identity.application.authentication import AuthenticationService
from app.identity.application.mfa import MfaService
from app.identity.application.security import BruteForceGuard, InMemoryRateLimitStore
from app.identity.domain.entities import User
from app.identity.domain.exceptions import InvalidMfaCodeError
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.messaging.idempotency import InMemoryIdempotencyStore
from app.platform_core.security.encryption import FieldEncryptionService
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeAuditRecordSink

pytestmark = pytest.mark.asyncio

_PASSWORD = "Correct-Horse-Battery-9"
_RECOVERY_CODE_PEPPER = "test-recovery-pepper-with-at-least-32-characters"
_FIELD_ENCRYPTION_KEY = b"MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _make_services(uow) -> tuple[AuthenticationService, MfaService]:
    token_service = JwtTokenService(signing_key="a" * 32)
    auth_service = AuthenticationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        token_service=token_service,
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
    )
    mfa_service = MfaService(
        uow_factory=lambda: uow,
        encryption=FieldEncryptionService(_FIELD_ENCRYPTION_KEY),
        dispatcher=EventDispatcher(),
        authentication_service=auth_service,
        recovery_code_pepper=_RECOVERY_CODE_PEPPER,
        token_service=token_service,
        challenge_replay_store=InMemoryIdempotencyStore(),
        attempt_guard=BruteForceGuard(store=InMemoryRateLimitStore()),
    )
    return auth_service, mfa_service


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


async def test_login_stops_at_a_challenge_once_mfa_is_enrolled_and_confirmed(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    auth_service, mfa_service = _make_services(uow)

    enrollment = await mfa_service.start_totp_enrollment(user_id=user.id)
    code = pyotp.TOTP(enrollment.secret).now()
    await mfa_service.confirm_totp_enrollment(user_id=user.id, factor_id=enrollment.factor_id, code=code)

    login_result = await auth_service.login(
        org_id=OrgId(org.id), email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    # The whole point of MFA: a correct password alone must never be
    # enough to receive tokens once a factor is enrolled and confirmed.
    assert login_result.tokens is None
    assert login_result.mfa_challenge_token is not None


async def test_verify_mfa_challenge_with_the_correct_totp_code_issues_tokens(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    auth_service, mfa_service = _make_services(uow)

    enrollment = await mfa_service.start_totp_enrollment(user_id=user.id)
    setup_code = pyotp.TOTP(enrollment.secret).now()
    await mfa_service.confirm_totp_enrollment(user_id=user.id, factor_id=enrollment.factor_id, code=setup_code)

    login_result = await auth_service.login(
        org_id=OrgId(org.id), email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )
    assert login_result.mfa_challenge_token is not None

    challenge_code = pyotp.TOTP(enrollment.secret).now()
    tokens = await mfa_service.verify_mfa_challenge(
        challenge_token=login_result.mfa_challenge_token, code=challenge_code,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    assert tokens.access_token
    assert tokens.refresh_token


async def test_verify_mfa_challenge_rejects_an_incorrect_code(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, user = await _make_org_and_active_user(uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email)
    auth_service, mfa_service = _make_services(uow)

    enrollment = await mfa_service.start_totp_enrollment(user_id=user.id)
    setup_code = pyotp.TOTP(enrollment.secret).now()
    await mfa_service.confirm_totp_enrollment(user_id=user.id, factor_id=enrollment.factor_id, code=setup_code)

    login_result = await auth_service.login(
        org_id=OrgId(org.id), email=email, password=_PASSWORD,
        ip_address="127.0.0.1", device_info=None, remember_me=False,
    )

    with pytest.raises(InvalidMfaCodeError):
        await mfa_service.verify_mfa_challenge(
            challenge_token=login_result.mfa_challenge_token, code="000000",
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )


async def test_totp_enrollment_survives_service_restart_with_configured_key(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    _, user = await _make_org_and_active_user(
        uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email
    )
    _, first_service = _make_services(uow)
    enrollment = await first_service.start_totp_enrollment(user_id=user.id)

    _, restarted_service = _make_services(uow)
    codes = await restarted_service.confirm_totp_enrollment(
        user_id=user.id,
        factor_id=enrollment.factor_id,
        code=pyotp.TOTP(enrollment.secret).now(),
    )

    assert len(codes) == 10


async def test_mfa_challenge_token_is_single_use(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    org, user = await _make_org_and_active_user(
        uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email
    )
    auth_service, mfa_service = _make_services(uow)
    enrollment = await mfa_service.start_totp_enrollment(user_id=user.id)
    await mfa_service.confirm_totp_enrollment(
        user_id=user.id,
        factor_id=enrollment.factor_id,
        code=pyotp.TOTP(enrollment.secret).now(),
    )
    login_result = await auth_service.login(
        org_id=OrgId(org.id),
        email=email,
        password=_PASSWORD,
        ip_address="127.0.0.1",
        device_info=None,
        remember_me=False,
    )
    code = pyotp.TOTP(enrollment.secret).now()

    await mfa_service.verify_mfa_challenge(
        challenge_token=login_result.mfa_challenge_token,
        code=code,
        ip_address="127.0.0.1",
        device_info=None,
        remember_me=False,
    )
    with pytest.raises(InvalidMfaCodeError):
        await mfa_service.verify_mfa_challenge(
            challenge_token=login_result.mfa_challenge_token,
            code=code,
            ip_address="127.0.0.1",
            device_info=None,
            remember_me=False,
        )


async def test_sensitive_mfa_changes_reject_an_invalid_current_code(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    _, user = await _make_org_and_active_user(
        uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email,
    )
    _, mfa_service = _make_services(uow)
    enrollment = await mfa_service.start_totp_enrollment(user_id=user.id)
    await mfa_service.confirm_totp_enrollment(
        user_id=user.id, factor_id=enrollment.factor_id,
        code=pyotp.TOTP(enrollment.secret).now(),
    )

    with pytest.raises(InvalidMfaCodeError):
        await mfa_service.regenerate_recovery_codes(
            user_id=user.id, code="not-a-valid-code", ip_address="127.0.0.1",
        )
    with pytest.raises(InvalidMfaCodeError):
        await mfa_service.disable_mfa(
            user_id=user.id, code="not-a-valid-code", ip_address="127.0.0.1",
        )

    persisted_user = await uow.users.get_by_id(user.id)
    assert persisted_user.mfa_enabled is True
    assert len(await uow.mfa_factors.list_for_user(user.id)) == 11


async def test_sensitive_mfa_changes_accept_a_current_factor(uow) -> None:
    email = f"owner-{uuid.uuid4().hex[:12]}@example.com"
    _, user = await _make_org_and_active_user(
        uow, slug=f"acme-{uuid.uuid4().hex[:12]}", email=email,
    )
    _, mfa_service = _make_services(uow)
    enrollment = await mfa_service.start_totp_enrollment(user_id=user.id)
    old_codes = await mfa_service.confirm_totp_enrollment(
        user_id=user.id, factor_id=enrollment.factor_id,
        code=pyotp.TOTP(enrollment.secret).now(),
    )

    new_codes = await mfa_service.regenerate_recovery_codes(
        user_id=user.id, code=old_codes[0], ip_address="127.0.0.1",
    )
    assert len(new_codes) == 10
    assert set(new_codes).isdisjoint(old_codes)
    with pytest.raises(InvalidMfaCodeError):
        await mfa_service.regenerate_recovery_codes(
            user_id=user.id, code=old_codes[0], ip_address="127.0.0.1",
        )

    await mfa_service.disable_mfa(
        user_id=user.id, code=pyotp.TOTP(enrollment.secret).now(),
        ip_address="127.0.0.1",
    )
    persisted_user = await uow.users.get_by_id(user.id)
    assert persisted_user.mfa_enabled is False
    assert await uow.mfa_factors.list_for_user(user.id) == []
