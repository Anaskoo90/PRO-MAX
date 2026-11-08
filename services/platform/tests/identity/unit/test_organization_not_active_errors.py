"""Unit tests for the error contract of suspended organizations and refresh failures."""

from __future__ import annotations

import json
import re

import pytest
from app.identity.application.authentication import AuthenticationService, AuthPolicy
from app.identity.domain.entities import Session
from app.identity.domain.exceptions import (
    AccountNotActiveError,
    OrganizationNotActiveError,
    SessionNotFoundError,
)
from app.platform_core.errors.handlers import _handle_guilddesk_error, _map_status_code
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.error_codes import ErrorCode
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio

_POLICY = AuthPolicy()


def _auth(uow: FakeUnitOfWork) -> AuthenticationService:
    return AuthenticationService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(),
        token_service=JwtTokenService(signing_key="a" * 32), dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()), policy=_POLICY,
    )


async def test_organization_not_active_maps_to_403_with_its_own_code() -> None:
    exc = OrganizationNotActiveError("suspended")

    assert exc.code == ErrorCode.ORGANIZATION_NOT_ACTIVE
    assert _map_status_code(exc) == 403
    response = await _handle_guilddesk_error(None, exc)
    body = json.loads(response.body)
    assert response.status_code == 403
    assert body["code"] == "ORGANIZATION_NOT_ACTIVE"
    assert "suspended" in body["message"]


async def test_other_business_rule_errors_keep_their_422() -> None:
    assert _map_status_code(AccountNotActiveError("suspended")) == 422  # unrelated behavior unchanged


async def test_session_not_found_without_an_identifier_is_generic() -> None:
    exc = SessionNotFoundError()

    assert exc.message == "Session was not found"
    assert exc.entity_id is None


async def test_session_not_found_with_an_id_is_unchanged() -> None:
    session_id = new_uuid7()

    assert str(session_id) in SessionNotFoundError(session_id).message  # revoke_session(id) behavior intact


async def test_refresh_with_an_unknown_token_never_echoes_the_lookup_hash() -> None:
    raw = "an-unknown-refresh-token"
    lookup_hash = hash_for_lookup(raw, secret_pepper=_POLICY.refresh_token_pepper)

    with pytest.raises(SessionNotFoundError) as excinfo:
        await _auth(FakeUnitOfWork()).refresh(raw_refresh_token=raw)

    message = str(excinfo.value)
    assert lookup_hash not in message and raw not in message
    assert not re.search(r"[0-9a-f]{64}", message)


async def test_refresh_of_a_revoked_session_never_echoes_the_lookup_hash() -> None:
    uow = FakeUnitOfWork()
    raw = "a-revoked-refresh-token"
    lookup_hash = hash_for_lookup(raw, secret_pepper=_POLICY.refresh_token_pepper)
    session = Session.create(
        user_id=new_uuid7(), refresh_token_hash=lookup_hash, device_info=None, ip_address="127.0.0.1",
        remember_me=True,
    )
    session.revoke()
    await uow.sessions.add(session)

    with pytest.raises(SessionNotFoundError) as excinfo:
        await _auth(uow).refresh(raw_refresh_token=raw)

    assert lookup_hash not in str(excinfo.value)


async def test_refresh_for_a_session_whose_user_is_missing_does_not_leak_the_user_id() -> None:
    uow = FakeUnitOfWork()
    raw = "orphaned-session-token"
    orphan_user_id = new_uuid7()  # no such user
    session = Session.create(
        user_id=orphan_user_id,
        refresh_token_hash=hash_for_lookup(raw, secret_pepper=_POLICY.refresh_token_pepper),
        device_info=None, ip_address="127.0.0.1", remember_me=True,
    )
    await uow.sessions.add(session)

    with pytest.raises(SessionNotFoundError) as excinfo:
        await _auth(uow).refresh(raw_refresh_token=raw)

    assert str(orphan_user_id) not in str(excinfo.value)
