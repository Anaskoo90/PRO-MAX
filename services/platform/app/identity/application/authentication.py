"""
Authentication submodule: login, logout, refresh, JWT issuance, OAuth2/OIDC
login, session listing/revocation (device management), remember-me.

Every handler follows the same shape: open a UnitOfWork, load/mutate
aggregates, persist, pull + dispatch domain events, commit. Access tokens
are short-lived JWTs (platform_core.security.token); refresh tokens are
opaque random strings, looked up by HMAC hash (platform_core.security.hashing)
against identity.sessions.refresh_token_hash — never parsed client-side, so
there's no reason to pay JWT's structure/overhead for them.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.identity.application.dtos import AuthTokens, LoginResult, SessionDTO
from app.identity.domain.entities import Session, User
from app.identity.domain.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    SessionNotFoundError,
    UserNotFoundError,
)
from app.identity.domain.events import SessionRevoked, SuspiciousLoginDetected, UserLoggedIn, UserLoggedOut
from app.identity.domain.specifications import AccountLockoutSpecification
from app.identity.domain.value_objects import Email
from app.identity.application.ports import IdentityUnitOfWorkPort, OAuth2ClientPort
from app.identity.application.security import SecurityService
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.token import JwtTokenService
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import utcnow


@dataclass(frozen=True, slots=True)
class AuthPolicy:
    lockout_threshold: int = 5
    lockout_duration: timedelta = timedelta(minutes=15)
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_pepper: str = "change-me-in-production"  # see SecretProvider


class AuthenticationService:
    def __init__(
        self,
        *,
        uow_factory,
        password_hasher: PasswordHashingService,
        token_service: JwtTokenService,
        dispatcher: EventDispatcher,
        audit_logger: AuditLogger,
        security_service: SecurityService | None = None,
        policy: AuthPolicy = AuthPolicy(),
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._token_service = token_service
        self._dispatcher = dispatcher
        self._audit_logger = audit_logger
        self._security_service = security_service
        self._policy = policy

    async def login(
        self,
        *,
        org_id: OrgId,
        email: str,
        password: str,
        ip_address: str,
        device_info: dict | None,
        remember_me: bool,
    ) -> LoginResult:
        if self._security_service is not None:
            await self._security_service.check_login_allowed(org_id=org_id, ip_address=ip_address)

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(org_id, email.strip().lower())
            if user is None:
                raise InvalidCredentialsError()

            if AccountLockoutSpecification().is_satisfied_by(user):
                retry_after = int((user.locked_until - utcnow()).total_seconds()) if user.locked_until else 0
                raise AccountLockedError(retry_after_seconds=max(0, retry_after))

            if not self._password_hasher.verify(password, user.password_hash):
                user.record_failed_login(
                    lockout_threshold=self._policy.lockout_threshold,
                    lockout_duration=self._policy.lockout_duration,
                )
                await uow.users.update(user)
                await uow.commit()
                raise InvalidCredentialsError()

            user.assert_can_authenticate()

            if user.mfa_enabled:
                user.record_successful_login()
                await uow.users.update(user)
                await uow.commit()
                return LoginResult(mfa_challenge_user_id=user.id, mfa_available_factors=("totp", "recovery_code"))

            user.record_successful_login()
            suspicious = await self._is_suspicious(user_id=user.id, ip_address=ip_address)
            tokens, session = await self._issue_session(
                uow, user, ip_address=ip_address, device_info=device_info, remember_me=remember_me
            )
            await uow.users.update(user)
            events = user.pull_domain_events()
            events.append(UserLoggedIn(aggregate_id=user.id, session_id=session.id))
            if suspicious:
                events.append(SuspiciousLoginDetected(aggregate_id=user.id, session_id=session.id, ip_address=ip_address))
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            await self._audit_logger.record(
                org_id=org_id, actor_id=user.id, action="login", resource_type="user", resource_id=str(user.id)
            )
            return LoginResult(tokens=tokens)

    async def complete_mfa_challenge(self, *, user_id: EntityId, ip_address: str, device_info: dict | None, remember_me: bool) -> AuthTokens:
        """Called by mfa.py's VerifyMfaChallenge after a successful MFA
        check — kept here since session/token issuance is Authentication's
        responsibility, not MFA's."""
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            suspicious = await self._is_suspicious(user_id=user.id, ip_address=ip_address)
            tokens, session = await self._issue_session(
                uow, user, ip_address=ip_address, device_info=device_info, remember_me=remember_me
            )
            events = [UserLoggedIn(aggregate_id=user.id, session_id=session.id)]
            if suspicious:
                events.append(SuspiciousLoginDetected(aggregate_id=user.id, session_id=session.id, ip_address=ip_address))
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return tokens

    async def _is_suspicious(self, *, user_id: EntityId, ip_address: str) -> bool:
        if self._security_service is None:
            return False
        return await self._security_service.suspicious_login_detector.is_suspicious(
            user_id=user_id, ip_address=ip_address
        )

    async def _issue_session(
        self, uow: IdentityUnitOfWorkPort, user: User, *, ip_address: str, device_info: dict | None, remember_me: bool
    ) -> tuple[AuthTokens, Session]:
        raw_refresh_token = secrets.token_urlsafe(48)
        refresh_token_hash = hash_for_lookup(raw_refresh_token, secret_pepper=self._policy.refresh_token_pepper)
        session = Session.create(
            user_id=user.id,
            refresh_token_hash=refresh_token_hash,
            device_info=device_info,
            ip_address=ip_address,
            remember_me=remember_me,
        )
        await uow.sessions.add(session)
        access_token = self._token_service.issue_access_token(
            user_id=user.id, org_id=user.org_id, scopes=[], ttl=self._policy.access_token_ttl
        )
        tokens = AuthTokens(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in_seconds=int(self._policy.access_token_ttl.total_seconds()),
        )
        return tokens, session

    async def refresh(self, *, raw_refresh_token: str) -> AuthTokens:
        refresh_token_hash = hash_for_lookup(raw_refresh_token, secret_pepper=self._policy.refresh_token_pepper)
        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_refresh_token_hash(refresh_token_hash)
            if session is None or not session.is_active():
                raise SessionNotFoundError(refresh_token_hash)
            user = await uow.users.get_by_id(session.user_id)
            if user is None:
                raise UserNotFoundError(session.user_id)

            # Refresh-token rotation: the old token is revoked, a new one issued —
            # limits the blast radius of a leaked refresh token to a single use.
            session.revoke()
            await uow.sessions.update(session)
            tokens, new_session = await self._issue_session(
                uow, user, ip_address=session.ip_address, device_info=session.device_info, remember_me=session.remember_me
            )
            await uow.commit()
            return tokens

    async def logout(self, *, raw_refresh_token: str) -> None:
        refresh_token_hash = hash_for_lookup(raw_refresh_token, secret_pepper=self._policy.refresh_token_pepper)
        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_refresh_token_hash(refresh_token_hash)
            if session is None:
                return  # logout is idempotent
            session.revoke()
            await uow.sessions.update(session)
            await uow.commit()
            await self._dispatcher.dispatch(UserLoggedOut(aggregate_id=session.user_id, session_id=session.id))

    async def list_sessions(self, *, user_id: EntityId, current_session_id: EntityId | None) -> list[SessionDTO]:
        async with self._uow_factory() as uow:
            sessions = await uow.sessions.list_active_for_user(user_id)
            return [
                SessionDTO(
                    id=s.id,
                    device_label=s.device_label(),
                    ip_address=s.ip_address,
                    created_at=s.created_at,
                    expires_at=s.expires_at,
                    is_current=(s.id == current_session_id),
                )
                for s in sessions
            ]

    async def revoke_session(self, *, user_id: EntityId, session_id: EntityId) -> None:
        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_id(session_id)
            if session is None or session.user_id != user_id:
                raise SessionNotFoundError(session_id)
            session.revoke()
            await uow.sessions.update(session)
            await uow.commit()
            await self._dispatcher.dispatch(SessionRevoked(aggregate_id=user_id, session_id=session_id))


class OAuth2LoginService:
    """Find-or-create a local user from a verified external identity, then
    delegate to AuthenticationService for session/token issuance — external
    login is a user-provisioning concern layered on top of, not a
    replacement for, the core session model."""

    def __init__(
        self,
        *,
        uow_factory,
        oauth2_clients: dict[str, OAuth2ClientPort],
        authentication_service: AuthenticationService,
    ) -> None:
        self._uow_factory = uow_factory
        self._oauth2_clients = oauth2_clients
        self._authentication_service = authentication_service

    def build_authorization_url(self, provider_key: str) -> tuple[str, str]:
        return self._oauth2_clients[provider_key].build_authorization_url()

    async def login_with_callback(
        self, *, provider_key: str, code: str, org_id: OrgId, ip_address: str, device_info: dict | None
    ) -> AuthTokens:
        client = self._oauth2_clients[provider_key]
        token_response = await client.exchange_code(code)
        identity = await client.fetch_external_identity(token_response)

        async with self._uow_factory() as uow:
            user = None
            if identity.email:
                user = await uow.users.get_by_email(org_id, identity.email)
            if user is None:
                fallback_email = f"{identity.subject}@{provider_key}.oauth.guilddesk.local"
                user = User.register(
                    org_id=org_id,
                    email=Email(identity.email or fallback_email),
                    password_hash="",  # OAuth-only accounts have no local password
                    display_name=identity.display_name or identity.subject,
                )
                user.verify_email()  # provider already verified the email
                await uow.users.add(user)
                await uow.commit()

        return await self._authentication_service.complete_mfa_challenge(
            user_id=user.id, ip_address=ip_address, device_info=device_info, remember_me=False
        )
