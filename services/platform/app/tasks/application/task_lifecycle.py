"""Task Lifecycle + Priority submodules: status transitions (validated
against the project's resolved workflow) and priority changes."""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import TaskDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.tasks.application.workflow_management import resolve_workflow_for_project
from app.tasks.domain.audit import TasksAuditEventCategory, TasksAuditLogRecord
from app.tasks.domain.entities import Task
from app.tasks.domain.exceptions import TaskNotFoundError
from app.tasks.domain.workflow import TaskPriority, TaskStatus


def _to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, description=task.description,
        status=task.status.value, priority=task.priority.value, parent_task_id=task.parent_task_id,
        position=task.position, start_date=task.start_date, due_date=task.due_date, reminder_date=task.reminder_date,
        completion_date=task.completion_date, is_archived=task.is_archived, archived_at=task.archived_at,
        is_overdue=task.is_overdue(),
    )


class TaskLifecycleService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def change_status(self, *, task_id: EntityId, actor_user_id: UserId, status: TaskStatus) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            task.assert_not_deleted()
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            workflow = await resolve_workflow_for_project(uow, project_id=task.project_id)
            task.change_status(status, workflow=workflow)
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=task.org_id, category=TasksAuditEventCategory.TASK_CHANGE, action="task_status_changed",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(task.id),
                    metadata={"status": status.value},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def change_priority(self, *, task_id: EntityId, actor_user_id: UserId, priority: TaskPriority) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            task.assert_not_deleted()
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            task.change_priority(priority)
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)
