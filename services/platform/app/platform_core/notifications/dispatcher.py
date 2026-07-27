"""
Notification Dispatcher: routes a channel-agnostic NotificationRequest to
the right provider(s) and records delivery attempts. This is the
platform_core-level primitive the Notification Center (already consolidated
from 3 historically-fragmented implementations — see the Master
Architecture) builds its routing-rule engine on top of; it does not
reimplement per-channel logic itself.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.platform_core.logging.logger import get_logger
from app.platform_core.notifications.email_provider import EmailMessage, EmailProvider
from app.platform_core.notifications.push_provider import PushMessage, PushProvider
from app.platform_core.notifications.sms_provider import SmsMessage, SmsProvider

_logger = get_logger("notifications.dispatcher")


class NotificationChannel(StrEnum):
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"


class NotificationRequest(BaseModel):
    org_id: UUID
    channel: NotificationChannel
    recipient: str  # email address / device token / phone number, per channel
    subject: str | None = None
    body: str
    metadata: dict[str, Any] = {}


class NoProviderRegisteredError(Exception):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__(f"No provider registered for channel '{channel}'")


class NotificationDispatcher:
    def __init__(
        self,
        *,
        email_provider: EmailProvider | None = None,
        push_provider: PushProvider | None = None,
        sms_provider: SmsProvider | None = None,
    ) -> None:
        self._email_provider = email_provider
        self._push_provider = push_provider
        self._sms_provider = sms_provider

    async def dispatch(self, request: NotificationRequest) -> None:
        try:
            if request.channel == NotificationChannel.EMAIL:
                if self._email_provider is None:
                    raise NoProviderRegisteredError(request.channel)
                await self._email_provider.send(
                    EmailMessage(
                        to_address=request.recipient,
                        subject=request.subject or "",
                        html_body=request.body,
                    )
                )
            elif request.channel == NotificationChannel.PUSH:
                if self._push_provider is None:
                    raise NoProviderRegisteredError(request.channel)
                await self._push_provider.send(
                    PushMessage(
                        device_token=request.recipient,
                        title=request.subject or "",
                        body=request.body,
                        data=request.metadata,
                    )
                )
            elif request.channel == NotificationChannel.SMS:
                if self._sms_provider is None:
                    raise NoProviderRegisteredError(request.channel)
                await self._sms_provider.send(
                    SmsMessage(to_phone_number=request.recipient, body=request.body)
                )
        except Exception:
            await _logger.aerror(
                "notification_dispatch_failed", channel=request.channel, exc_info=True
            )
            raise
