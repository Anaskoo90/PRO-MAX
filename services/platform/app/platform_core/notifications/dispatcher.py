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
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from app.platform_core.logging.logger import get_logger
from app.platform_core.notifications.email_provider import EmailMessage, EmailProvider
from app.platform_core.notifications.push_provider import PushMessage, PushProvider
from app.platform_core.notifications.sms_provider import SmsMessage, SmsProvider

_logger = get_logger("notifications.dispatcher")


class NotificationChannel(StrEnum):
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"
    IN_APP = "in_app"


class NotificationRequest(BaseModel):
    org_id: UUID
    channel: NotificationChannel
    recipient: str  # email address / device token / phone number, per channel
    recipient_user_id: UUID | None = None
    subject: str | None = None
    body: str
    # Only this explicitly safe copy is stored and exposed in the in-app
    # inbox. Transactional bodies may contain one-time verification/reset
    # tokens and must never be persisted as notification content.
    in_app_body: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationDeliveryRecorder(Protocol):
    async def begin(self, request: NotificationRequest) -> UUID: ...
    async def mark_delivered(self, notification_id: UUID) -> None: ...
    async def mark_failed(
        self, notification_id: UUID, *, failure_type: str
    ) -> None: ...


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
        delivery_recorder: NotificationDeliveryRecorder | None = None,
    ) -> None:
        self._email_provider = email_provider
        self._push_provider = push_provider
        self._sms_provider = sms_provider
        self._delivery_recorder = delivery_recorder

    def set_delivery_recorder(self, recorder: NotificationDeliveryRecorder) -> None:
        if self._delivery_recorder is not None:
            raise ValueError("Notification delivery recorder is already configured")
        self._delivery_recorder = recorder

    async def dispatch(self, request: NotificationRequest) -> None:
        notification_id: UUID | None = None
        if self._delivery_recorder is not None:
            notification_id = await self._delivery_recorder.begin(request)
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
            elif request.channel == NotificationChannel.IN_APP:
                if self._delivery_recorder is None:
                    raise NoProviderRegisteredError(request.channel)
        except Exception as exc:
            if notification_id is not None and self._delivery_recorder is not None:
                try:
                    await self._delivery_recorder.mark_failed(
                        notification_id,
                        failure_type=type(exc).__name__,
                    )
                except Exception:
                    await _logger.aerror(
                        "notification_failure_recording_failed",
                        notification_id=str(notification_id),
                        exc_info=True,
                    )
            await _logger.aerror(
                "notification_dispatch_failed", channel=request.channel, exc_info=True
            )
            raise
        else:
            if notification_id is not None and self._delivery_recorder is not None:
                try:
                    await self._delivery_recorder.mark_delivered(notification_id)
                except Exception:
                    # The provider already accepted the message. Do not make
                    # callers retry and create a duplicate external delivery.
                    await _logger.aerror(
                        "notification_success_recording_failed",
                        notification_id=str(notification_id),
                        exc_info=True,
                    )
