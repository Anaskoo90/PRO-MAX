"""
Anti-Corruption Layer: the only file in this bounded context permitted to
depend on Tasks & Work Management. Wraps Tasks' own public application
services (TaskService, TaskQueryService, TaskLifecycleService,
TaskSchedulingService, TaskAssignmentService, LabelService — all public
attributes on TasksModule, never Tasks' infrastructure) and translates
Tasks' types into this context's own TaskSummary (application.ports), and
Tasks' InvalidTaskStatusTransitionError into this context's own
TaskStatusRejectedError so nothing here ever leaks Tasks' exception types.

TaskSummary bundles assignee_ids/label_ids up front (unlike Boards' own
TasksTaskContextAdapter, which exposes them as separate calls) since
Workflow Engine's condition evaluator needs all of a task's attributes in
one shot to check ASSIGNEE/LABEL conditions without extra round trips.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.tasks.application.label_management import LabelService
from app.tasks.application.task_assignment import TaskAssignmentService
from app.tasks.application.task_lifecycle import TaskLifecycleService
from app.tasks.application.task_management import TaskService
from app.tasks.application.task_scheduling import TaskSchedulingService
from app.tasks.domain.exceptions import InvalidTaskStatusTransitionError, TaskNotFoundError
from app.tasks.domain.workflow import TaskPriority, TaskStatus as TasksTaskStatus
from app.workflow_engine.application.ports import TaskStatusRejectedError, TaskSummary


class TasksWorkflowContextAdapter:
    def __init__(
        self, *, task_service: TaskService, task_lifecycle_service: TaskLifecycleService,
        task_scheduling_service: TaskSchedulingService, task_assignment_service: TaskAssignmentService,
        label_service: LabelService,
    ) -> None:
        self._task_service = task_service
        self._task_lifecycle_service = task_lifecycle_service
        self._task_scheduling_service = task_scheduling_service
        self._task_assignment_service = task_assignment_service
        self._label_service = label_service

    async def get_task(self, *, task_id: UUID) -> TaskSummary | None:
        try:
            task = await self._task_service.get(task_id=task_id)
        except TaskNotFoundError:
            return None
        assignments = await self._task_assignment_service.list_assignments(task_id=task_id)
        labels = await self._label_service.list_labels_for_task(task_id=task_id)
        return TaskSummary(
            id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, status=task.status,
            priority=task.priority, assignee_ids=tuple(a.user_id for a in assignments), label_ids=tuple(l.id for l in labels),
        )

    async def change_task_status(self, *, task_id: UUID, actor_user_id: UUID, status: str) -> None:
        try:
            tasks_status = TasksTaskStatus(status)
        except ValueError as exc:
            raise TaskStatusRejectedError(f"'{status}' is not a recognized task status") from exc
        try:
            await self._task_lifecycle_service.change_status(task_id=task_id, actor_user_id=actor_user_id, status=tasks_status)
        except InvalidTaskStatusTransitionError as exc:
            raise TaskStatusRejectedError(str(exc)) from exc

    async def change_priority(self, *, task_id: UUID, actor_user_id: UUID, priority: str) -> None:
        try:
            tasks_priority = TaskPriority(priority)
        except ValueError as exc:
            raise TaskStatusRejectedError(f"'{priority}' is not a recognized task priority") from exc
        await self._task_lifecycle_service.change_priority(task_id=task_id, actor_user_id=actor_user_id, priority=tasks_priority)

    async def set_due_date(self, *, task_id: UUID, actor_user_id: UUID, due_date: datetime) -> None:
        await self._task_scheduling_service.set_dates(task_id=task_id, actor_user_id=actor_user_id, due_date=due_date)

    async def assign_user(self, *, task_id: UUID, actor_user_id: UUID, assignee_user_id: UUID) -> None:
        await self._task_assignment_service.assign(task_id=task_id, actor_user_id=actor_user_id, assignee_user_id=assignee_user_id)
