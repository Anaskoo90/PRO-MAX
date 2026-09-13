from __future__ import annotations

import pytest
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.workflow_engine.application.action_execution import ActionExecutor
from app.workflow_engine.application.ports import UserSummary
from app.workflow_engine.domain.entities import ActionType, WorkflowAction

from tests.workflow_engine.unit.fakes import (
    FakeTasksContext,
    FakeUserDirectory,
    FakeWebhookExecutor,
)


class _RecordingEmailProvider:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message) -> None:
        self.sent.append(message)


class _RecordingDeliveryRecorder:
    def __init__(self) -> None:
        self.requests = []
        self.delivered = []

    async def begin(self, request):
        notification_id = new_uuid7()
        self.requests.append(request)
        return notification_id

    async def mark_delivered(self, notification_id) -> None:
        self.delivered.append(notification_id)

    async def mark_failed(self, notification_id, *, failure_type: str) -> None:
        raise AssertionError(f"Unexpected notification failure: {failure_type}")


@pytest.mark.asyncio
async def test_send_notification_action_delivers_through_the_wired_email_provider() -> None:
    recipient_id = UserId(new_uuid7())
    org_id = OrgId(new_uuid7())
    email_provider = _RecordingEmailProvider()
    executor = ActionExecutor(
        tasks_context=FakeTasksContext(),
        notification_dispatcher=NotificationDispatcher(email_provider=email_provider),
        user_directory=FakeUserDirectory(
            {
                recipient_id: UserSummary(
                    id=recipient_id,
                    org_id=org_id,
                    email="recipient@example.com",
                    display_name="Recipient",
                )
            }
        ),
        webhook_executor=FakeWebhookExecutor(),
    )
    action = WorkflowAction.create(
        transition_id=EntityId(new_uuid7()),
        action_type=ActionType.SEND_NOTIFICATION,
        config={
            "recipient_user_id": str(recipient_id),
            "subject": "Workflow moved",
            "body": "The task is ready.",
        },
        position=1024.0,
    )

    await executor.execute(
        object(),
        action,
        workflow_id=EntityId(new_uuid7()),
        task_id=EntityId(new_uuid7()),
        org_id=org_id,
        actor_user_id=UserId(new_uuid7()),
    )

    assert len(email_provider.sent) == 1
    assert email_provider.sent[0].to_address == "recipient@example.com"
    assert email_provider.sent[0].subject == "Workflow moved"
    assert email_provider.sent[0].html_body == "The task is ready."


@pytest.mark.asyncio
async def test_send_notification_action_rejects_a_cross_tenant_recipient() -> None:
    recipient_id = UserId(new_uuid7())
    email_provider = _RecordingEmailProvider()
    executor = ActionExecutor(
        tasks_context=FakeTasksContext(),
        notification_dispatcher=NotificationDispatcher(email_provider=email_provider),
        user_directory=FakeUserDirectory(
            {
                recipient_id: UserSummary(
                    id=recipient_id,
                    org_id=OrgId(new_uuid7()),
                    email="foreign@example.com",
                    display_name="Foreign Recipient",
                )
            }
        ),
        webhook_executor=FakeWebhookExecutor(),
    )
    action = WorkflowAction.create(
        transition_id=EntityId(new_uuid7()),
        action_type=ActionType.SEND_NOTIFICATION,
        config={"recipient_user_id": str(recipient_id), "body": "Private update"},
        position=1024.0,
    )

    with pytest.raises(ValueError, match="does not belong"):
        await executor.execute(
            object(),
            action,
            workflow_id=EntityId(new_uuid7()),
            task_id=EntityId(new_uuid7()),
            org_id=OrgId(new_uuid7()),
            actor_user_id=UserId(new_uuid7()),
        )

    assert email_provider.sent == []


@pytest.mark.asyncio
async def test_send_notification_action_supports_durable_in_app_delivery() -> None:
    recipient_id = UserId(new_uuid7())
    org_id = OrgId(new_uuid7())
    recorder = _RecordingDeliveryRecorder()
    executor = ActionExecutor(
        tasks_context=FakeTasksContext(),
        notification_dispatcher=NotificationDispatcher(delivery_recorder=recorder),
        user_directory=FakeUserDirectory(
            {
                recipient_id: UserSummary(
                    id=recipient_id,
                    org_id=org_id,
                    email="recipient@example.com",
                    display_name="Recipient",
                )
            }
        ),
        webhook_executor=FakeWebhookExecutor(),
    )
    action = WorkflowAction.create(
        transition_id=EntityId(new_uuid7()),
        action_type=ActionType.SEND_NOTIFICATION,
        config={
            "recipient_user_id": str(recipient_id),
            "channel": "in_app",
            "subject": "Workflow moved",
            "body": "The task is ready.",
        },
        position=1024.0,
    )

    await executor.execute(
        object(),
        action,
        workflow_id=EntityId(new_uuid7()),
        task_id=EntityId(new_uuid7()),
        org_id=org_id,
        actor_user_id=UserId(new_uuid7()),
    )

    assert len(recorder.requests) == 1
    assert recorder.requests[0].channel.value == "in_app"
    assert recorder.requests[0].recipient_user_id == recipient_id
    assert recorder.requests[0].in_app_body == "The task is ready."
    assert len(recorder.delivered) == 1


@pytest.mark.asyncio
async def test_send_notification_action_rejects_channels_without_recipient_addresses() -> None:
    recipient_id = UserId(new_uuid7())
    org_id = OrgId(new_uuid7())
    email_provider = _RecordingEmailProvider()
    executor = ActionExecutor(
        tasks_context=FakeTasksContext(),
        notification_dispatcher=NotificationDispatcher(email_provider=email_provider),
        user_directory=FakeUserDirectory(
            {
                recipient_id: UserSummary(
                    id=recipient_id,
                    org_id=org_id,
                    email="recipient@example.com",
                    display_name="Recipient",
                )
            }
        ),
        webhook_executor=FakeWebhookExecutor(),
    )
    action = WorkflowAction.create(
        transition_id=EntityId(new_uuid7()),
        action_type=ActionType.SEND_NOTIFICATION,
        config={
            "recipient_user_id": str(recipient_id),
            "channel": "sms",
            "body": "The task is ready.",
        },
        position=1024.0,
    )

    with pytest.raises(ValueError, match="only email and in_app"):
        await executor.execute(
            object(),
            action,
            workflow_id=EntityId(new_uuid7()),
            task_id=EntityId(new_uuid7()),
            org_id=org_id,
            actor_user_id=UserId(new_uuid7()),
        )

    assert email_provider.sent == []
