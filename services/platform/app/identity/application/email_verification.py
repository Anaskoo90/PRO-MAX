"""
Email Verification submodule: verification tokens, workflow, resend,
expiration rules.

Subscribes to UserRegistered (dispatched by UserManagementService) rather
than being called directly — wired in composition.py. This is also why the
handler is named on_user_registered instead of a command-style name: it's
an event subscriber, not a caller-invoked command.
"""

from __future__ import annotations

import secrets

from app.identity.domain.entities import EmailVerificationToken
from app.identity.domain.events import UserRegistered
from app.identity.domain.exceptions import (
    InvalidTokenError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    UserNotFoundError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.logger import get_logger
from app.platform_core.notifications.dispatcher import (
    NoProviderRegisteredError,
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.security.hashing import hash_for_lookup
from app.platform_core.shared_kernel.types import EntityId, OrgId

_logger = get_logger("identity.email_verification")

_TOKEN_PEPPER = "change-me-in-production"  # see platform_core.security.secrets_provider


class EmailVerificationService:
    def __init__(
        self,
        *,
        uow_factory,
        notification_dispatcher: NotificationDispatcher,
        dispatcher: EventDispatcher,
        verification_link_base_url: str = "https://app.guilddesk.local/verify-email",
    ) -> None:
        self._uow_factory = uow_factory
        self._notification_dispatcher = notification_dispatcher
        self._dispatcher = dispatcher
        self._verification_link_base_url = verification_link_base_url

    async def on_user_registered(self, event: UserRegistered) -> None:
        await self.send_verification(user_id=EntityId(event.aggregate_id), org_id=OrgId(event.org_id), email=event.email)

    async def send_verification(self, *, user_id: EntityId, org_id: OrgId, email: str) -> None:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER)

        async with self._uow_factory() as uow:
            await uow.email_verification_tokens.invalidate_outstanding_for_user(user_id)
            await uow.email_verification_tokens.add(
                EmailVerificationToken.create(user_id=user_id, token_hash=token_hash)
            )
            await uow.commit()

        try:
            await self._notification_dispatcher.dispatch(
                NotificationRequest(
                    org_id=org_id,
                    channel=NotificationChannel.EMAIL,
                    recipient=email,
                    subject="Verify your GuildDesk email address",
                    body=f"{self._verification_link_base_url}?token={raw_token}",
                )
            )
        except NoProviderRegisteredError:
            # No email provider is wired in this environment yet (a real
            # SES/SendGrid/etc. integration is a deployment-time decision,
            # not made in platform_core — see EmailProvider's docstring).
            # The verification token is already persisted and resend_verification
            # exists for when a provider is configured, so this must not fail
            # the registration request that triggered it.
            await _logger.awarning("email_verification_send_skipped_no_provider", user_id=str(user_id))

    async def resend_verification(self, *, user_id: EntityId) -> None:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
        await self.send_verification(user_id=user.id, org_id=user.org_id, email=str(user.email))

    async def verify_email(self, *, raw_token: str) -> None:
        token_hash = hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER)
        async with self._uow_factory() as uow:
            token = await uow.email_verification_tokens.get_by_token_hash(token_hash)
            if token is None:
                raise InvalidTokenError("email_verification")
            if token.is_consumed():
                raise TokenAlreadyUsedError("email_verification")
            if token.is_expired():
                raise TokenExpiredError("email_verification")

            user = await uow.users.get_by_id(token.user_id)
            if user is None:
                raise UserNotFoundError(token.user_id)

            token.consume()
            await uow.email_verification_tokens.update(token)
            user.verify_email()
            await uow.users.update(user)
            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
