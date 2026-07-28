"""
Task Relationships submodule: parent/subtask, dependencies, blocked-by,
related tasks. Cycle prevention walks sibling aggregates the same way
Identity's Team/Role hierarchy and Projects' Team hierarchy do — the
domain entities can't do this alone since a cycle check inherently spans
more than one aggregate instance.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.tasks.application.authorization_helpers import TaskAuthorization
from app.tasks.application.dtos import TaskDependencyDTO, TaskDTO, TaskRelationDTO
from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.tasks.domain.audit import TasksAuditEventCategory, TasksAuditLogRecord
from app.tasks.domain.entities import Task, TaskDependency, TaskRelation
from app.tasks.domain.events import TaskDependencyAdded, TaskDependencyRemoved, TaskRelationAdded, TaskRelationRemoved
from app.tasks.domain.workflow import TERMINAL_STATUSES
from app.tasks.domain.exceptions import (
    TaskCannotBeOwnParentError,
    TaskCannotDependOnItselfError,
    TaskDependencyAlreadyExistsError,
    TaskDependencyCycleError,
    TaskDependencyNotFoundError,
    TaskNotFoundError,
    TaskParentCycleError,
    TaskRelationAlreadyExistsError,
    TaskRelationNotFoundError,
)


def _to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id, project_id=task.project_id, org_id=task.org_id, title=task.title, description=task.description,
        status=task.status.value, priority=task.priority.value, parent_task_id=task.parent_task_id,
        position=task.position, start_date=task.start_date, due_date=task.due_date, reminder_date=task.reminder_date,
        completion_date=task.completion_date, is_archived=task.is_archived, archived_at=task.archived_at,
        is_overdue=task.is_overdue(),
    )


class TaskRelationshipService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TaskAuthorization(permission_checker=permission_checker, project_context=project_context)

    # --- Parent / subtask ----------------------------------------------

    async def set_parent(self, *, task_id: EntityId, actor_user_id: UserId, parent_task_id: EntityId | None) -> TaskDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            if parent_task_id is not None:
                if parent_task_id == task_id:
                    raise TaskCannotBeOwnParentError()
                cursor: EntityId | None = parent_task_id
                visited: set[EntityId] = set()
                while cursor is not None:
                    if cursor == task_id:
                        raise TaskParentCycleError()
                    if cursor in visited:
                        break
                    visited.add(cursor)
                    ancestor = await uow.tasks.get_by_id(cursor)
                    cursor = ancestor.parent_task_id if ancestor else None

            task.set_parent(parent_task_id)
            await uow.tasks.update(task)
            events = task.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(task)

    async def list_subtasks(self, *, parent_task_id: EntityId) -> list[TaskDTO]:
        async with self._uow_factory() as uow:
            subtasks = await uow.tasks.list_subtasks(parent_task_id)
            return [_to_dto(t) for t in subtasks]

    # --- Dependencies (Blocked By) ---------------------------------------

    async def add_dependency(self, *, task_id: EntityId, actor_user_id: UserId, depends_on_task_id: EntityId) -> TaskDependencyDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            if depends_on_task_id == task_id:
                raise TaskCannotDependOnItselfError()
            if await uow.tasks.get_by_id(depends_on_task_id) is None:
                raise TaskNotFoundError(depends_on_task_id)
            if await uow.task_dependencies.get(task_id, depends_on_task_id) is not None:
                raise TaskDependencyAlreadyExistsError()

            # Cycle check: would adding this edge let depends_on_task_id's
            # dependency chain eventually reach back to task_id?
            visited: set[EntityId] = set()
            frontier = [depends_on_task_id]
            while frontier:
                current = frontier.pop()
                if current == task_id:
                    raise TaskDependencyCycleError()
                if current in visited:
                    continue
                visited.add(current)
                for dep in await uow.task_dependencies.list_dependencies(current):
                    frontier.append(dep.depends_on_task_id)

            dependency = TaskDependency.create(task_id=task_id, depends_on_task_id=depends_on_task_id)
            await uow.task_dependencies.add(dependency)
            await uow.audit_logs.add(
                TasksAuditLogRecord.create(
                    org_id=task.org_id, category=TasksAuditEventCategory.RELATIONSHIP_CHANGE, action="dependency_added",
                    actor_user_id=actor_user_id, resource_type="task", resource_id=str(task_id),
                    metadata={"depends_on_task_id": str(depends_on_task_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch(TaskDependencyAdded(aggregate_id=task_id, depends_on_task_id=depends_on_task_id))
            return TaskDependencyDTO(id=dependency.id, task_id=dependency.task_id, depends_on_task_id=dependency.depends_on_task_id)

    async def remove_dependency(self, *, task_id: EntityId, actor_user_id: UserId, depends_on_task_id: EntityId) -> None:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            dependency = await uow.task_dependencies.get(task_id, depends_on_task_id)
            if dependency is None:
                raise TaskDependencyNotFoundError(task_id, depends_on_task_id)
            await uow.task_dependencies.delete(dependency.id)
            await uow.commit()
            await self._dispatcher.dispatch(TaskDependencyRemoved(aggregate_id=task_id, depends_on_task_id=depends_on_task_id))

    async def list_blocking_tasks(self, *, task_id: EntityId) -> list[TaskDTO]:
        """"Blocked By": the tasks that must complete before this one can,
        i.e. this task's outgoing dependency edges."""
        async with self._uow_factory() as uow:
            dependencies = await uow.task_dependencies.list_dependencies(task_id)
            tasks = await uow.tasks.list_by_ids([d.depends_on_task_id for d in dependencies])
            return [_to_dto(t) for t in tasks]

    async def is_blocked(self, *, task_id: EntityId) -> bool:
        async with self._uow_factory() as uow:
            dependencies = await uow.task_dependencies.list_dependencies(task_id)
            blocking_tasks = await uow.tasks.list_by_ids([d.depends_on_task_id for d in dependencies])
            return any(t.status not in TERMINAL_STATUSES for t in blocking_tasks)

    # --- Related tasks (symmetric, non-blocking) -------------------------

    async def add_related_task(self, *, task_id: EntityId, actor_user_id: UserId, related_task_id: EntityId) -> TaskRelationDTO:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            if await uow.tasks.get_by_id(related_task_id) is None:
                raise TaskNotFoundError(related_task_id)
            if await uow.task_relations.get(task_id, related_task_id) is not None or await uow.task_relations.get(related_task_id, task_id) is not None:
                raise TaskRelationAlreadyExistsError()

            relation = TaskRelation.create(task_id=task_id, related_task_id=related_task_id)
            await uow.task_relations.add(relation)
            await uow.commit()
            await self._dispatcher.dispatch(TaskRelationAdded(aggregate_id=task_id, related_task_id=related_task_id))
            return TaskRelationDTO(id=relation.id, task_id=relation.task_id, related_task_id=relation.related_task_id)

    async def remove_related_task(self, *, task_id: EntityId, actor_user_id: UserId, related_task_id: EntityId) -> None:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            await self._authorization.assert_can_manage(project_id=task.project_id, org_id=task.org_id, user_id=actor_user_id)

            relation = await uow.task_relations.get(task_id, related_task_id) or await uow.task_relations.get(related_task_id, task_id)
            if relation is None:
                raise TaskRelationNotFoundError(task_id, related_task_id)
            await uow.task_relations.delete(relation.id)
            await uow.commit()
            await self._dispatcher.dispatch(TaskRelationRemoved(aggregate_id=task_id, related_task_id=related_task_id))

    async def list_related_tasks(self, *, task_id: EntityId) -> list[TaskDTO]:
        async with self._uow_factory() as uow:
            relations = await uow.task_relations.list_for_task(task_id)
            related_ids = [r.related_task_id for r in relations]
            tasks = await uow.tasks.list_by_ids(related_ids)
            return [_to_dto(t) for t in tasks]
