"""
Anti-Corruption Layer: the only file in this bounded context permitted to
depend on Tasks & Work Management. Wraps Tasks' own public application
services (TaskService, TaskQueryService, TaskLifecycleService,
TaskAssignmentService, LabelService — all public attributes on
TasksModule, never Tasks' infrastructure) and translates Tasks' TaskDTO
into this context's own TaskSummary (application.ports), and Tasks'
InvalidTaskStatusTransitionError into this context's own
TaskStatusRejectedError so nothing here ever leaks Tasks' exception types.
"""

from __future__ import annotations

from uuid import UUID

from app.tasks.application.task_assignment import TaskAssignmentService
from app.tasks.application.task_lifecycle import TaskLifecycleService
from app.tasks.application.task_management import TaskService
from app.tasks.application.task_query_service import TaskQueryService
from app.tasks.application.label_management import LabelService
from app.tasks.domain.exceptions import InvalidTaskStatusTransitionError, TaskNotFoundError
from app.tasks.domain.workflow import TaskStatus as TasksTaskStatus
from app.boards.application.ports import TaskStatusRejectedError, TaskSummary


class TasksTaskContextAdapter:
    def __init__(
        self, *, task_service: TaskService, task_query_service: TaskQueryService,
        task_lifecycle_service: TaskLifecycleService, task_assignment_service: TaskAssignmentService,
        label_service: LabelService,
    ) -> None:
        self._task_service = task_service
        self._task_query_service = task_query_service
        self._task_lifecycle_service = task_lifecycle_service
        self._task_assignment_service = task_assignment_service
        self._label_service = label_service

    async def get_task(self, *, task_id: UUID) -> TaskSummary | None:
        try:
            task = await self._task_service.get(task_id=task_id)
        except TaskNotFoundError:
            return None
        return TaskSummary(id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, status=task.status, priority=task.priority)

    async def list_tasks_for_project(self, *, project_id: UUID, include_archived: bool = False) -> list[TaskSummary]:
        tasks = await self._task_query_service.list_for_project(project_id=project_id, include_archived=include_archived)
        return [
            TaskSummary(id=t.id, project_id=t.project_id, org_id=t.org_id, title=t.title, status=t.status, priority=t.priority)
            for t in tasks
        ]

    async def change_task_status(self, *, task_id: UUID, actor_user_id: UUID, status: str) -> None:
        try:
            tasks_status = TasksTaskStatus(status)
        except ValueError as exc:
            raise TaskStatusRejectedError(f"'{status}' is not a recognized task status") from exc
        try:
            await self._task_lifecycle_service.change_status(task_id=task_id, actor_user_id=actor_user_id, status=tasks_status)
        except InvalidTaskStatusTransitionError as exc:
            raise TaskStatusRejectedError(str(exc)) from exc

    async def list_assignee_ids(self, *, task_id: UUID) -> list[UUID]:
        assignments = await self._task_assignment_service.list_assignments(task_id=task_id)
        return [a.user_id for a in assignments]

    async def list_label_ids(self, *, task_id: UUID) -> list[UUID]:
        labels = await self._label_service.list_labels_for_task(task_id=task_id)
        return [l.id for l in labels]
