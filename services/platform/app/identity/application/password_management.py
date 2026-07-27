"""
Password Management submodule: hashing (delegates to
platform_core.security.hashing), policies (delegates to
platform_core.security.password_policy), reset, change, history,
expiration.

Password hashing and policy enforcement are deliberately *not*
reimplemented here — they're platform_core concerns reused as-is, per the
"extend an existing shared mechanism rather than invent a parallel one"
discipline. This module only adds what's genuinely Identity-specific:
reset-token workflow, reuse-history checks, and expiration.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from app.identity.domain.entities import PasswordHistoryEntry, PasswordResetToken
from app.identity.domain.events import PasswordResetRequested
from app.identity.domain.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    PasswordReuseError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    UserNotFoundError,
    WeakPasswordError,
)
from app.identity.domain.specifications import PasswordReuseSpecification
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import (
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY, PasswordPolicy
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import utcnow

_TOKEN_PEPPER = "change-me-in-production"  # see platform_core.security.secrets_provider


class PasswordManagementService:
    def __init__(
        self,
        *,
        uow_factory,
        password_hasher: PasswordHashingService,
        notification_dispatcher: NotificationDispatcher,
        dispatcher: EventDispatcher,
        password_policy: PasswordPolicy = DEFAULT_PASSWORD_POLICY,
        history_check_depth: int = 5,
        max_password_age: timedelta = timedelta(days=90),
        reset_link_base_url: str = "https://app.guilddesk.local/reset-password",
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._notification_dispatcher = notification_dispatcher
        self._dispatcher = dispatcher
        self._password_policy = password_policy
        self._history_check_depth = history_check_depth
        self._max_password_age = max_password_age
        self._reset_link_base_url = reset_link_base_url

    async def _apply_new_password(self, uow, user, new_password: str) -> None:
        violations = self._password_policy.violations(new_password)
        if violations:
            raise WeakPasswordError(violations)

        history = await uow.password_history.recent_for_user(user.id, limit=self._history_check_depth)
        if PasswordReuseSpecification(self._password_hasher).is_satisfied_by((new_password, history)):
            raise PasswordReuseError()

        new_hash = self._password_hasher.hash(new_password)
        user.change_password(new_hash)
        await uow.users.update(user)
        await uow.password_history.add(PasswordHistoryEntry.create(user_id=user.id, password_hash=new_hash))

    async def change_password(self, *, user_id: EntityId, current_password: str, new_password: str) -> None:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            if not self._password_hasher.verify(current_password, user.password_hash):
                raise InvalidCredentialsError()

            await self._apply_new_password(uow, user, new_password)
            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def request_password_reset(self, *, org_id: OrgId, email: str) -> None:
        """Always completes without revealing whether the email is
        registered — the response is identical either way; only the side
        effect (an email being sent) differs."""
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(org_id, email.strip().lower())
            if user is None:
                return

            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER)
            await uow.password_reset_tokens.invalidate_outstanding_for_user(user.id)
            await uow.password_reset_tokens.add(PasswordResetToken.create(user_id=user.id, token_hash=token_hash))
            await uow.commit()
            await self._dispatcher.dispatch(PasswordResetRequested(aggregate_id=user.id))

        await self._notification_dispatcher.dispatch(
            NotificationRequest(
                org_id=org_id,
                channel=NotificationChannel.EMAIL,
                recipient=email,
                subject="Reset your GuildDesk password",
                body=f"{self._reset_link_base_url}?token={raw_token}",
            )
        )

    async def reset_password(self, *, raw_token: str, new_password: str) -> None:
        token_hash = hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER)
        async with self._uow_factory() as uow:
            token = await uow.password_reset_tokens.get_by_token_hash(token_hash)
            if token is None:
                raise InvalidTokenError("password_reset")
            if token.is_consumed():
                raise TokenAlreadyUsedError("password_reset")
            if token.is_expired():
                raise TokenExpiredError("password_reset")

            user = await uow.users.get_by_id(token.user_id)
            if user is None:
                raise UserNotFoundError(token.user_id)

            await self._apply_new_password(uow, user, new_password)
            token.consume()
            await uow.password_reset_tokens.update(token)

            # Reset implies compromise-or-forgotten-credential recovery —
            # revoke every existing session so a leaked prior credential
            # can't keep an active session alive past the reset.
            for session in await uow.sessions.list_active_for_user(user.id):
                session.revoke()
                await uow.sessions.update(session)

            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def is_password_expired(self, *, user_id: EntityId) -> bool:
        async with self._uow_factory() as uow:
            history = await uow.password_history.recent_for_user(user_id, limit=1)
            if not history:
                return False
            return (utcnow() - history[0].created_at) > self._max_password_age
