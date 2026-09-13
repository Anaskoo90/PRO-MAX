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


@pytest.mark.asyncio
async def test_send_notification_action_delivers_through_the_wired_email_provider() -> None:
    recipient_id = UserId(new_uuid7())
    email_provider = _RecordingEmailProvider()
    executor = ActionExecutor(
        tasks_context=FakeTasksContext(),
        notification_dispatcher=NotificationDispatcher(email_provider=email_provider),
        user_directory=FakeUserDirectory(
            {
                recipient_id: UserSummary(
                    id=recipient_id,
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
        org_id=OrgId(new_uuid7()),
        actor_user_id=UserId(new_uuid7()),
    )

    assert len(email_provider.sent) == 1
    assert email_provider.sent[0].to_address == "recipient@example.com"
    assert email_provider.sent[0].subject == "Workflow moved"
    assert email_provider.sent[0].html_body == "The task is ready."
