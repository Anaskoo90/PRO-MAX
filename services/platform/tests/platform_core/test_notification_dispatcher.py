from __future__ import annotations

import pytest
from app.platform_core.notifications.dispatcher import (
    NoProviderRegisteredError,
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[NotificationRequest] = []
        self.delivered: list = []
        self.failed: list[tuple] = []

    async def begin(self, request: NotificationRequest):
        self.requests.append(request)
        return new_uuid7()

    async def mark_delivered(self, notification_id) -> None:
        self.delivered.append(notification_id)

    async def mark_failed(self, notification_id, *, failure_type: str) -> None:
        self.failed.append((notification_id, failure_type))


class _EmailProvider:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.messages = []

    async def send(self, message) -> None:
        if self.failure is not None:
            raise self.failure
        self.messages.append(message)


def _request(channel: NotificationChannel) -> NotificationRequest:
    return NotificationRequest(
        org_id=new_uuid7(),
        channel=channel,
        recipient="user@example.com",
        recipient_user_id=new_uuid7(),
        subject="Subject",
        body="External body",
        in_app_body="Safe body",
    )


async def test_successful_delivery_is_recorded() -> None:
    recorder = _Recorder()
    provider = _EmailProvider()
    dispatcher = NotificationDispatcher(
        email_provider=provider, delivery_recorder=recorder
    )

    await dispatcher.dispatch(_request(NotificationChannel.EMAIL))

    assert len(provider.messages) == 1
    assert len(recorder.requests) == 1
    assert len(recorder.delivered) == 1
    assert recorder.failed == []


async def test_failed_delivery_is_recorded_and_the_provider_error_propagates() -> None:
    recorder = _Recorder()
    dispatcher = NotificationDispatcher(
        email_provider=_EmailProvider(failure=RuntimeError("provider unavailable")),
        delivery_recorder=recorder,
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await dispatcher.dispatch(_request(NotificationChannel.EMAIL))

    assert recorder.delivered == []
    assert len(recorder.failed) == 1
    assert recorder.failed[0][1] == "RuntimeError"


async def test_in_app_delivery_uses_the_durable_recorder_without_an_external_provider() -> None:
    recorder = _Recorder()
    dispatcher = NotificationDispatcher(delivery_recorder=recorder)

    await dispatcher.dispatch(_request(NotificationChannel.IN_APP))

    assert len(recorder.delivered) == 1
    assert recorder.failed == []


async def test_in_app_delivery_requires_durable_storage() -> None:
    dispatcher = NotificationDispatcher()

    with pytest.raises(NoProviderRegisteredError):
        await dispatcher.dispatch(_request(NotificationChannel.IN_APP))
