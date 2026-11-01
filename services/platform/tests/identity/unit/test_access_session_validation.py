from __future__ import annotations

from datetime import timedelta

import pytest
from app.identity.application.authentication import AuthenticationService
from app.identity.domain.entities import Session, User
from app.identity.domain.value_objects import Email
from app.identity.presentation.deps import get_current_user_claims
from app.platform_core.errors.api_exceptions import UnauthorizedError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import EntityId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from fastapi.security import HTTPAuthorizationCredentials

from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio

_TOKEN_SERVICE = JwtTokenService(signing_key="a" * 32)


def _make_service(uow: FakeUnitOfWork) -> AuthenticationService:
    return AuthenticationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        token_service=_TOKEN_SERVICE,
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
    )


async def _authenticate(
    *,
    service: AuthenticationService,
    user_id,
    org_id,
    session_id,
):
    token = _TOKEN_SERVICE.issue_access_token(
        user_id=user_id,
        org_id=org_id,
        scopes=[],
        session_id=session_id,
    )
    return await get_current_user_claims(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        token_service=_TOKEN_SERVICE,
        authentication_service=service,
    )


def _session(*, user_id, expires_at=None) -> Session:
    now = utcnow()
    return Session(
        id=EntityId(new_uuid7()),
        user_id=user_id,
        refresh_token_hash="lookup-hash",
        device_info=None,
        ip_address="127.0.0.1",
        remember_me=False,
        created_at=now,
        expires_at=expires_at or now + timedelta(hours=1),
    )


def _user(*, org_id) -> User:
    user = User.register(
        org_id=org_id, email=Email("member@example.com"), password_hash="hash", display_name="Member"
    )
    user.verify_email()
    return user


async def test_active_session_bound_to_the_claimed_user_is_accepted() -> None:
    org_id = new_uuid7()
    user = _user(org_id=org_id)
    user_id = user.id
    session = _session(user_id=user_id)
    uow = FakeUnitOfWork()
    await uow.users.add(user)
    await uow.sessions.add(session)

    claims = await _authenticate(
        service=_make_service(uow),
        user_id=user_id,
        org_id=org_id,
        session_id=session.id,
    )

    assert claims.subject_user_id == user_id
    assert claims.session_id == session.id


async def test_access_token_without_a_session_identifier_is_rejected() -> None:
    user_id = new_uuid7()
    token = _TOKEN_SERVICE.issue_access_token(
        user_id=user_id,
        org_id=new_uuid7(),
        scopes=[],
    )

    with pytest.raises(UnauthorizedError):
        await get_current_user_claims(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            token_service=_TOKEN_SERVICE,
            authentication_service=_make_service(FakeUnitOfWork()),
        )


async def test_access_token_with_a_missing_persisted_session_is_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        await _authenticate(
            service=_make_service(FakeUnitOfWork()),
            user_id=new_uuid7(),
            org_id=new_uuid7(),
            session_id=new_uuid7(),
        )


async def test_access_token_bound_to_another_users_session_is_rejected() -> None:
    session = _session(user_id=new_uuid7())
    uow = FakeUnitOfWork()
    await uow.sessions.add(session)

    with pytest.raises(UnauthorizedError):
        await _authenticate(
            service=_make_service(uow),
            user_id=new_uuid7(),
            org_id=new_uuid7(),
            session_id=session.id,
        )


async def test_access_token_with_a_revoked_session_is_rejected() -> None:
    user_id = new_uuid7()
    session = _session(user_id=user_id)
    session.revoke()
    uow = FakeUnitOfWork()
    await uow.sessions.add(session)

    with pytest.raises(UnauthorizedError):
        await _authenticate(
            service=_make_service(uow),
            user_id=user_id,
            org_id=new_uuid7(),
            session_id=session.id,
        )


async def test_access_token_with_an_expired_session_is_rejected() -> None:
    user_id = new_uuid7()
    session = _session(user_id=user_id, expires_at=utcnow() - timedelta(seconds=1))
    uow = FakeUnitOfWork()
    await uow.sessions.add(session)

    with pytest.raises(UnauthorizedError):
        await _authenticate(
            service=_make_service(uow),
            user_id=user_id,
            org_id=new_uuid7(),
            session_id=session.id,
        )


@pytest.mark.parametrize("deactivate", [False, True], ids=["suspended", "deactivated"])
async def test_access_token_for_a_suspended_or_deactivated_user_is_rejected(deactivate: bool) -> None:
    """Defense in depth: even if a session was somehow left unrevoked, an
    account that is no longer ACTIVE must not authenticate."""
    org_id = new_uuid7()
    user = _user(org_id=org_id)
    session = _session(user_id=user.id)
    uow = FakeUnitOfWork()
    await uow.users.add(user)
    await uow.sessions.add(session)
    if deactivate:
        user.deactivate()
    else:
        user.suspend(reason="policy violation")
    await uow.users.update(user)

    with pytest.raises(UnauthorizedError):
        await _authenticate(
            service=_make_service(uow), user_id=user.id, org_id=org_id, session_id=session.id
        )


async def test_access_token_whose_user_record_is_missing_is_rejected() -> None:
    user_id = new_uuid7()
    session = _session(user_id=user_id)
    uow = FakeUnitOfWork()
    await uow.sessions.add(session)

    with pytest.raises(UnauthorizedError):
        await _authenticate(
            service=_make_service(uow), user_id=user_id, org_id=new_uuid7(), session_id=session.id
        )
