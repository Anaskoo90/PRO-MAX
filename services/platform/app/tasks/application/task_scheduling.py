"""Dates submodule: start/due/reminder date management. Overdue *detection*
(the query) lives in task_query_service.py / Task.is_overdue — this module
owns the mutation path plus the platform-wide overdue count used by the
scheduled observability job (see composition.py's JobScheduler wiring)."""

from __future__ import annotations

from datetime import datetime

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import TaskDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.tasks.domain.entities import Task
from app.tasks.domain.exceptions import TaskNotFoundError


def _to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, description=task.description,
        status=task.status.value, priority=task.priority.value, parent_task_id=task.parent_task_id,
        position=task.position, start_date=task.start_date, due_date=task.due_date, reminder_date=task.reminder_date,
        completion_date=task.completion_date, is_archived=task.is_archived, archived_at=task.archived_at,
        is_overdue=task.is_overdue(),
    )


class TaskSchedulingService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def set_dates(
        self, *, task_id: EntityId, actor_user_id: UserId, start_date: datetime | None = None,
        due_date: datetime | None = None, reminder_date: datetime | None = None,
    ) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            task.assert_not_deleted()
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            task.set_dates(start_date=start_date, due_date=due_date, reminder_date=reminder_date)
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def count_overdue_all(self) -> int:
        """Used by the recurring overdue-scan job (composition.py) —
        platform-wide, not project-scoped, since the job runs independent
        of any single request's tenant context."""
        async with self._uow_factory() as uow:
            return await uow.tasks.count_overdue_all()
