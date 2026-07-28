"""
Task Ordering submodule: position, drag-and-drop reordering, manual sort,
automatic ordering. Manual positioning uses fractional indexing
(compute_position_between) so a drag-and-drop move only ever rewrites the
single moved row — never its siblings. Automatic ordering is a query-time
sort mode, not a persisted position: it never touches the stored
`position` column.
"""

from __future__ import annotations

from enum import StrEnum

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import TaskDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.tasks.domain.entities import Task, compute_position_between
from app.tasks.domain.exceptions import TaskNotFoundError
from app.tasks.domain.workflow import TaskPriority


def _to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, description=task.description,
        status=task.status.value, priority=task.priority.value, parent_task_id=task.parent_task_id,
        position=task.position, start_date=task.start_date, due_date=task.due_date, reminder_date=task.reminder_date,
        completion_date=task.completion_date, is_archived=task.is_archived, archived_at=task.archived_at,
        is_overdue=task.is_overdue(),
    )


class AutoOrderStrategy(StrEnum):
    PRIORITY_DESC = "priority_desc"
    DUE_DATE_ASC = "due_date_asc"


_PRIORITY_RANK = {TaskPriority.CRITICAL: 0, TaskPriority.HIGH: 1, TaskPriority.MEDIUM: 2, TaskPriority.LOW: 3}


class TaskOrderingService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def move_task(
        self, *, task_id: EntityId, actor_user_id: UserId, previous_task_id: EntityId | None, next_task_id: EntityId | None,
    ) -> TaskDTO:
        """Drag & Drop Ordering / Manual Sort: the caller identifies the
        new position purely by its new neighbors in the list (as any
        drag-and-drop UI naturally reports it), not by a raw numeric
        position value."""
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            task.assert_not_deleted()
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            previous_position = None
            if previous_task_id is not None:
                previous_task = await uow.tasks.get_by_id(previous_task_id)
                previous_position = previous_task.position if previous_task else None
            next_position = None
            if next_task_id is not None:
                next_task = await uow.tasks.get_by_id(next_task_id)
                next_position = next_task.position if next_task else None

            new_position = compute_position_between(previous_position, next_position)
            task.set_position(new_position)
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def list_auto_ordered(self, *, project_id: EntityId, strategy: AutoOrderStrategy) -> list[TaskDTO]:
        """Automatic Ordering: a read-only alternate sort, never persisted
        — the stored `position` column (used for manual drag-and-drop
        order) is untouched by this."""
        async with self._uow_factory() as uow:
            tasks = await uow.tasks.list_for_project(project_id)

        if strategy == AutoOrderStrategy.PRIORITY_DESC:
            tasks.sort(key=lambda t: _PRIORITY_RANK[t.priority])
        elif strategy == AutoOrderStrategy.DUE_DATE_ASC:
            tasks.sort(key=lambda t: (t.due_date is None, t.due_date))
        return [_to_dto(t) for t in tasks]
