"""
Workflow Actions submodule (5): Assign User, Change Priority, Send
Notification, Create Comment, Create Activity Log, Update Due Date,
Execute Webhook.

Shared by both the immediate-execution path (execution_service.py, right
after a transition applies) and the delayed/scheduled path
(automation_service.py's job, for actions whose trigger_mode deferred
them) — one executor, two callers, so a SCHEDULED "send notification"
behaves identically to an IMMEDIATE one.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.platform_core.logging.logger import get_logger
from app.platform_core.notifications.dispatcher import NotificationChannel, NotificationDispatcher, NotificationRequest
from app.workflow_engine.application.ports import TasksContextPort, UserDirectoryPort, WebhookExecutorPort
from app.workflow_engine.domain.entities import ActionType, ActivityEntryType, WorkflowAction, WorkflowActivityEntry
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId

_logger = get_logger("workflow_engine.action_execution")


class ActionExecutor:
    def __init__(
        self, *, tasks_context: TasksContextPort, notification_dispatcher: NotificationDispatcher,
        user_directory: UserDirectoryPort, webhook_executor: WebhookExecutorPort,
    ) -> None:
        self._tasks_context = tasks_context
        self._notification_dispatcher = notification_dispatcher
        self._user_directory = user_directory
        self._webhook_executor = webhook_executor

    async def execute(
        self, uow, action: WorkflowAction, *, workflow_id: EntityId, task_id: EntityId, org_id: OrgId, actor_user_id: UserId,
    ) -> None:
        if action.action_type == ActionType.ASSIGN_USER:
            assignee_user_id = UUID(action.config["assignee_user_id"])
            await self._tasks_context.assign_user(task_id=task_id, actor_user_id=actor_user_id, assignee_user_id=assignee_user_id)

        elif action.action_type == ActionType.CHANGE_PRIORITY:
            await self._tasks_context.change_priority(task_id=task_id, actor_user_id=actor_user_id, priority=action.config["priority"])

        elif action.action_type == ActionType.UPDATE_DUE_DATE:
            due_date = datetime.fromisoformat(action.config["due_date"])
            await self._tasks_context.set_due_date(task_id=task_id, actor_user_id=actor_user_id, due_date=due_date)

        elif action.action_type == ActionType.SEND_NOTIFICATION:
            recipient = await self._user_directory.get_by_id(user_id=UUID(action.config["recipient_user_id"]))
            if recipient is not None:
                await self._notification_dispatcher.dispatch(
                    NotificationRequest(
                        org_id=org_id, channel=NotificationChannel(action.config.get("channel", "email")),
                        recipient=recipient.email, subject=action.config.get("subject"),
                        body=action.config.get("body", ""),
                    )
                )

        elif action.action_type == ActionType.CREATE_COMMENT:
            entry = WorkflowActivityEntry.create(
                workflow_id=workflow_id, task_id=task_id, transition_id=action.transition_id,
                entry_type=ActivityEntryType.COMMENT, body=action.config.get("body", ""), actor_user_id=actor_user_id,
            )
            await uow.activity_entries.add(entry)

        elif action.action_type == ActionType.CREATE_ACTIVITY_LOG:
            entry = WorkflowActivityEntry.create(
                workflow_id=workflow_id, task_id=task_id, transition_id=action.transition_id,
                entry_type=ActivityEntryType.ACTIVITY_LOG, body=action.config.get("message", ""), actor_user_id=actor_user_id,
            )
            await uow.activity_entries.add(entry)

        elif action.action_type == ActionType.EXECUTE_WEBHOOK:
            payload = action.config.get("payload") or {"workflow_id": str(workflow_id), "task_id": str(task_id)}
            await self._webhook_executor.execute(url=action.config["url"], payload=payload)

        else:
            await _logger.awarning("workflow_action_type_unrecognized", action_type=action.action_type.value)
