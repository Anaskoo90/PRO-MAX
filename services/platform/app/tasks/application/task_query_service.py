"""
Queries (CQRS read side): list/filter/search, overdue detection, subtasks.
Deliberately has no write path — every method here is read-only, mirroring
the same UnitOfWork/DTO conventions the Commands side (TaskService) uses,
so callers don't need two different plumbing styles for reads vs. writes.
"""

from __future__ import annotations

from app.platform_core.shared_kernel.types import EntityId, UserId
from app.tasks.application.dtos import TaskDTO, TaskListFilter
from app.tasks.domain.entities import Task
from app.tasks.domain.workflow import TaskPriority, TaskStatus


def _to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, description=task.description,
        status=task.status.value, priority=task.priority.value, parent_task_id=task.parent_task_id,
        position=task.position, start_date=task.start_date, due_date=task.due_date, reminder_date=task.reminder_date,
        completion_date=task.completion_date, is_archived=task.is_archived, archived_at=task.archived_at,
        is_overdue=task.is_overdue(),
    )


class TaskQueryService:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def list_for_project(self, *, project_id: EntityId, include_archived: bool = False) -> list[TaskDTO]:
        async with self._uow_factory() as uow:
            tasks = await uow.tasks.list_for_project(project_id, include_archived=include_archived)
            return [_to_dto(t) for t in tasks]

    async def search(self, *, project_id: EntityId, filters: TaskListFilter) -> list[TaskDTO]:
        """Labels' "Filtering"/"Search" requirements, combined with status/
        priority/parent filters into one query — see TaskListFilter."""
        async with self._uow_factory() as uow:
            tasks = await uow.tasks.search(
                project_id,
                status=TaskStatus(filters.status) if filters.status else None,
                priority=TaskPriority(filters.priority) if filters.priority else None,
                label_id=EntityId(filters.label_id) if filters.label_id else None,
                assignee_user_id=UserId(filters.assignee_user_id) if filters.assignee_user_id else None,
                search_text=filters.search_text,
                include_archived=filters.include_archived,
                parent_task_id=EntityId(filters.parent_task_id) if filters.parent_task_id else None,
            )
            return [_to_dto(t) for t in tasks]

    async def list_subtasks(self, *, parent_task_id: EntityId) -> list[TaskDTO]:
        async with self._uow_factory() as uow:
            tasks = await uow.tasks.list_subtasks(parent_task_id)
            return [_to_dto(t) for t in tasks]

    async def list_overdue_for_project(self, *, project_id: EntityId) -> list[TaskDTO]:
        async with self._uow_factory() as uow:
            tasks = await uow.tasks.list_overdue_for_project(project_id)
            return [_to_dto(t) for t in tasks]
