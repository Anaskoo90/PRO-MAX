"""
Task Aggregate submodule (Commands): create, update, delete, archive,
restore, duplicate. Read-only listing/search lives in task_query_service.py
— the CQRS split is deliberately literal at the module level this time
(TaskService = commands, TaskQueryService = queries), a natural extension
of the same command/query-shaped methods Identity and Projects already
used, not a redesign of their style.
"""

from __future__ import annotations

from datetime import datetime

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import TaskDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.tasks.domain.audit import TasksAuditEventCategory, TasksAuditLogRecord
from app.tasks.domain.entities import Task
from app.tasks.domain.exceptions import InsufficientTaskPermissionError, TaskNotFoundError
from app.tasks.domain.workflow import TaskPriority


def _to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, description=task.description,
        status=task.status.value, priority=task.priority.value, parent_task_id=task.parent_task_id,
        position=task.position, start_date=task.start_date, due_date=task.due_date, reminder_date=task.reminder_date,
        completion_date=task.completion_date, is_archived=task.is_archived, archived_at=task.archived_at,
        is_overdue=task.is_overdue(),
    )


class TaskService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)
        self._project_context = project_context

    async def create_task(
        self, *, project_id: EntityId, org_id: OrgId, actor_user_id: UserId, title: str, description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM, parent_task_id: EntityId | None = None,
        start_date: datetime | None = None, due_date: datetime | None = None, reminder_date: datetime | None = None,
    ) -> TaskDTO:
        # Tenant-isolation check: the caller's own org_id (from their JWT
        # claims) must match the target project's org — otherwise a user
        # could operate on another organization's project by guessing its
        # id. Existing-task mutations below don't repeat this check; the
        # project-membership lookup itself is the security boundary there,
        # matching Projects & Workspaces' own established precedent.
        await self._authorization.assert_project_accessible(project_id=project_id, org_id=org_id)
        if not await self._authorization.can_manage(project_id=project_id, org_id=org_id, user_id=actor_user_id):
            raise InsufficientTaskPermissionError(("owner", "admin", "contributor"))

        async with self._uow_factory() as uow:
            existing_count = len(await uow.tasks.list_for_project(project_id, include_archived=True))
            position = (existing_count + 1) * 1024.0
            task = Task.create(
                project_id=project_id, org_id=org_id, title=title, description=description, priority=priority,
                parent_task_id=parent_task_id, position=position, start_date=start_date, due_date=due_date,
                reminder_date=reminder_date,
            )
            await uow.tasks.add(task)
            events = task.pull_domain_events()
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=org_id, category=TasksAuditEventCategory.TASK_CHANGE, action="task_created",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(task.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def get(self, *, task_id: EntityId) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            return _to_dto(task)

    async def _load_and_authorize(self, uow, *, task_id: EntityId, actor_user_id: UserId) -> Task:
        task = await uow.tasks.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        task.assert_not_deleted()
        await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)
        return task

    async def update(self, *, task_id: EntityId, actor_user_id: UserId, title: str | None, description: str | None) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await self._load_and_authorize(uow, task_id=task_id, actor_user_id=actor_user_id)
            task.update(title=title, description=description)
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def archive(self, *, task_id: EntityId, actor_user_id: UserId) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await self._load_and_authorize(uow, task_id=task_id, actor_user_id=actor_user_id)
            task.archive()
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=task.org_id, category=TasksAuditEventCategory.TASK_CHANGE, action="task_archived",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(task.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def restore(self, *, task_id: EntityId, actor_user_id: UserId) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await self._load_and_authorize(uow, task_id=task_id, actor_user_id=actor_user_id)
            task.restore()
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def delete(self, *, task_id: EntityId, actor_user_id: UserId) -> None:
        """Soft delete (deleted_at) — distinct from archive, per the
        platform-wide convention that entity tables never hard-delete."""
        async with self._uow_factory() as uow:
            task = await self._load_and_authorize(uow, task_id=task_id, actor_user_id=actor_user_id)
            task.mark_deleted()
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=task.org_id, category=TasksAuditEventCategory.TASK_CHANGE, action="task_deleted",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(task.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def duplicate(self, *, task_id: EntityId, actor_user_id: UserId, title: str | None = None) -> TaskDTO:
        async with self._uow_factory() as uow:
            source = await uow.tasks.get_by_id(task_id)
            if source is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=source.project_id, org_id=source.org_id, user_id=actor_user_id)

            duplicate = Task.duplicate_from(source, title=title)
            existing_count = len(await uow.tasks.list_for_project(source.project_id, include_archived=True))
            duplicate.set_position((existing_count + 1) * 1024.0)
            events = duplicate.pull_domain_events()  # captures TaskDuplicated + the TaskReordered from set_position
            await uow.tasks.add(duplicate)
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=duplicate.org_id, category=TasksAuditEventCategory.TASK_CHANGE, action="task_duplicated",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(duplicate.id),
                    metadata={"source_task_id": str(source.id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(duplicate)
