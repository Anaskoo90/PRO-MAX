"""SQLAlchemy-backed implementations of the Tasks & Work Management repository Protocols."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.domain.audit import TasksAuditEventCategory, TasksAuditLogRecord
from app.tasks.domain.entities import (
    Label,
    Task,
    TaskAssignment,
    TaskAssignmentHistoryRecord,
    TaskDependency,
    TaskLabel,
    TaskRelation,
)
from app.tasks.domain.workflow import TERMINAL_STATUSES, TaskPriority, TaskStatus, WorkflowDefinition
from app.platform_core.shared_kernel.utils import utcnow
from app.tasks.infrastructure import mappers
from app.tasks.infrastructure.orm_models import (
    LabelOrmModel,
    TaskAssignmentHistoryOrmModel,
    TaskAssignmentOrmModel,
    TaskDependencyOrmModel,
    TaskLabelOrmModel,
    TaskOrmModel,
    TaskRelationOrmModel,
    TasksAuditLogOrmModel,
    WorkflowDefinitionOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: EntityId) -> Task | None:
        row = await self._session.get(TaskOrmModel, task_id)
        return mappers.task_to_domain(row) if row and row.deleted_at is None else None

    async def list_for_project(self, project_id: EntityId, *, include_archived: bool = False) -> list[Task]:
        stmt = select(TaskOrmModel).where(TaskOrmModel.project_id == project_id, TaskOrmModel.deleted_at.is_(None))
        if not include_archived:
            stmt = stmt.where(TaskOrmModel.is_archived.is_(False))
        stmt = stmt.order_by(TaskOrmModel.position)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_to_domain(r) for r in rows]

    async def list_subtasks(self, parent_task_id: EntityId) -> list[Task]:
        stmt = select(TaskOrmModel).where(
            TaskOrmModel.parent_task_id == parent_task_id, TaskOrmModel.deleted_at.is_(None)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_to_domain(r) for r in rows]

    async def list_by_ids(self, task_ids: list[EntityId]) -> list[Task]:
        if not task_ids:
            return []
        stmt = select(TaskOrmModel).where(TaskOrmModel.id.in_(task_ids), TaskOrmModel.deleted_at.is_(None))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_to_domain(r) for r in rows]

    async def list_overdue_for_project(self, project_id: EntityId) -> list[Task]:
        terminal_values = [s.value for s in TERMINAL_STATUSES]
        # due_date is TIMESTAMPTZ on the wire, but the ORM column maps to a
        # timezone-naive DateTime() bind type — asyncpg rejects a tz-aware
        # Python datetime bound against that naive-typed parameter ("can't
        # subtract offset-naive and offset-aware datetimes"), so the
        # comparison value is stripped to naive UTC at this query boundary
        # only; utcnow() itself and every in-memory/domain use stay tz-aware.
        now_naive = utcnow().replace(tzinfo=None)
        stmt = select(TaskOrmModel).where(
            TaskOrmModel.project_id == project_id,
            TaskOrmModel.deleted_at.is_(None),
            TaskOrmModel.due_date.is_not(None),
            TaskOrmModel.due_date < now_naive,
            TaskOrmModel.status.notin_(terminal_values),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_to_domain(r) for r in rows]

    async def count_overdue_all(self) -> int:
        terminal_values = [s.value for s in TERMINAL_STATUSES]
        now_naive = utcnow().replace(tzinfo=None)
        stmt = select(func.count()).select_from(TaskOrmModel).where(
            TaskOrmModel.deleted_at.is_(None),
            TaskOrmModel.due_date.is_not(None),
            TaskOrmModel.due_date < now_naive,
            TaskOrmModel.status.notin_(terminal_values),
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def search(
        self,
        project_id: EntityId,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        label_id: EntityId | None = None,
        assignee_user_id=None,
        search_text: str | None = None,
        include_archived: bool = False,
        parent_task_id: EntityId | None = None,
    ) -> list[Task]:
        stmt = select(TaskOrmModel).where(TaskOrmModel.project_id == project_id, TaskOrmModel.deleted_at.is_(None))
        if not include_archived:
            stmt = stmt.where(TaskOrmModel.is_archived.is_(False))
        if status is not None:
            stmt = stmt.where(TaskOrmModel.status == status.value)
        if priority is not None:
            stmt = stmt.where(TaskOrmModel.priority == priority.value)
        if parent_task_id is not None:
            stmt = stmt.where(TaskOrmModel.parent_task_id == parent_task_id)
        if label_id is not None:
            stmt = stmt.join(TaskLabelOrmModel, TaskLabelOrmModel.task_id == TaskOrmModel.id).where(
                TaskLabelOrmModel.label_id == label_id
            )
        if assignee_user_id is not None:
            stmt = stmt.join(TaskAssignmentOrmModel, TaskAssignmentOrmModel.task_id == TaskOrmModel.id).where(
                TaskAssignmentOrmModel.user_id == assignee_user_id
            )
        if search_text:
            like_pattern = f"%{search_text}%"
            stmt = stmt.where(or_(TaskOrmModel.title.ilike(like_pattern), TaskOrmModel.description.ilike(like_pattern)))
        stmt = stmt.order_by(TaskOrmModel.position).distinct()
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_to_domain(r) for r in rows]

    async def add(self, task: Task) -> None:
        self._session.add(mappers.task_to_orm(task))

    async def update(self, task: Task) -> None:
        row = await self._session.get(TaskOrmModel, task.id)
        if row is None:
            raise ValueError(f"Task {task.id} not found for update")
        if row.version != task.version:
            raise ConcurrencyConflictError("Task", task.id)
        mappers.task_to_orm(task, row)
        row.version = task.version + 1
        task.version += 1


class SqlAlchemyTaskAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: EntityId, user_id: UserId) -> TaskAssignment | None:
        stmt = select(TaskAssignmentOrmModel).where(
            TaskAssignmentOrmModel.task_id == task_id, TaskAssignmentOrmModel.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.task_assignment_to_domain(row) if row else None

    async def list_for_task(self, task_id: EntityId) -> list[TaskAssignment]:
        stmt = select(TaskAssignmentOrmModel).where(TaskAssignmentOrmModel.task_id == task_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_assignment_to_domain(r) for r in rows]

    async def list_for_user(self, user_id: UserId) -> list[TaskAssignment]:
        stmt = select(TaskAssignmentOrmModel).where(TaskAssignmentOrmModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_assignment_to_domain(r) for r in rows]

    async def add(self, assignment: TaskAssignment) -> None:
        self._session.add(mappers.task_assignment_to_orm(assignment))

    async def update(self, assignment: TaskAssignment) -> None:
        row = await self._session.get(TaskAssignmentOrmModel, assignment.id)
        if row is None:
            raise ValueError(f"TaskAssignment {assignment.id} not found for update")
        row.is_primary = assignment.is_primary

    async def delete(self, assignment_id: EntityId) -> None:
        row = await self._session.get(TaskAssignmentOrmModel, assignment_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyTaskAssignmentHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: TaskAssignmentHistoryRecord) -> None:
        self._session.add(mappers.task_assignment_history_to_orm(record))

    async def list_for_task(self, task_id: EntityId) -> list[TaskAssignmentHistoryRecord]:
        stmt = (
            select(TaskAssignmentHistoryOrmModel)
            .where(TaskAssignmentHistoryOrmModel.task_id == task_id)
            .order_by(TaskAssignmentHistoryOrmModel.occurred_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_assignment_history_to_domain(r) for r in rows]


class SqlAlchemyLabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, label_id: EntityId) -> Label | None:
        row = await self._session.get(LabelOrmModel, label_id)
        return mappers.label_to_domain(row) if row else None

    async def get_by_name(self, project_id: EntityId, name: str) -> Label | None:
        stmt = select(LabelOrmModel).where(LabelOrmModel.project_id == project_id, LabelOrmModel.name == name)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.label_to_domain(row) if row else None

    async def list_for_project(self, project_id: EntityId) -> list[Label]:
        stmt = select(LabelOrmModel).where(LabelOrmModel.project_id == project_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.label_to_domain(r) for r in rows]

    async def add(self, label: Label) -> None:
        self._session.add(mappers.label_to_orm(label))

    async def update(self, label: Label) -> None:
        row = await self._session.get(LabelOrmModel, label.id)
        if row is None:
            raise ValueError(f"Label {label.id} not found for update")
        if row.version != label.version:
            raise ConcurrencyConflictError("Label", label.id)
        mappers.label_to_orm(label, row)
        row.version = label.version + 1
        label.version += 1

    async def delete(self, label_id: EntityId) -> None:
        row = await self._session.get(LabelOrmModel, label_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyTaskLabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: EntityId, label_id: EntityId) -> TaskLabel | None:
        stmt = select(TaskLabelOrmModel).where(TaskLabelOrmModel.task_id == task_id, TaskLabelOrmModel.label_id == label_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.task_label_to_domain(row) if row else None

    async def list_for_task(self, task_id: EntityId) -> list[TaskLabel]:
        stmt = select(TaskLabelOrmModel).where(TaskLabelOrmModel.task_id == task_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_label_to_domain(r) for r in rows]

    async def list_task_ids_for_label(self, label_id: EntityId) -> list[EntityId]:
        stmt = select(TaskLabelOrmModel.task_id).where(TaskLabelOrmModel.label_id == label_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [EntityId(r) for r in rows]

    async def add(self, task_label: TaskLabel) -> None:
        self._session.add(mappers.task_label_to_orm(task_label))

    async def delete(self, task_label_id: EntityId) -> None:
        row = await self._session.get(TaskLabelOrmModel, task_label_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyTaskDependencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: EntityId, depends_on_task_id: EntityId) -> TaskDependency | None:
        stmt = select(TaskDependencyOrmModel).where(
            TaskDependencyOrmModel.task_id == task_id, TaskDependencyOrmModel.depends_on_task_id == depends_on_task_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.task_dependency_to_domain(row) if row else None

    async def list_dependencies(self, task_id: EntityId) -> list[TaskDependency]:
        stmt = select(TaskDependencyOrmModel).where(TaskDependencyOrmModel.task_id == task_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_dependency_to_domain(r) for r in rows]

    async def list_dependents(self, task_id: EntityId) -> list[TaskDependency]:
        stmt = select(TaskDependencyOrmModel).where(TaskDependencyOrmModel.depends_on_task_id == task_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_dependency_to_domain(r) for r in rows]

    async def add(self, dependency: TaskDependency) -> None:
        self._session.add(mappers.task_dependency_to_orm(dependency))

    async def delete(self, dependency_id: EntityId) -> None:
        row = await self._session.get(TaskDependencyOrmModel, dependency_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyTaskRelationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: EntityId, related_task_id: EntityId) -> TaskRelation | None:
        stmt = select(TaskRelationOrmModel).where(
            TaskRelationOrmModel.task_id == task_id, TaskRelationOrmModel.related_task_id == related_task_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.task_relation_to_domain(row) if row else None

    async def list_for_task(self, task_id: EntityId) -> list[TaskRelation]:
        stmt = select(TaskRelationOrmModel).where(TaskRelationOrmModel.task_id == task_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.task_relation_to_domain(r) for r in rows]

    async def add(self, relation: TaskRelation) -> None:
        self._session.add(mappers.task_relation_to_orm(relation))

    async def delete(self, relation_id: EntityId) -> None:
        row = await self._session.get(TaskRelationOrmModel, relation_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyWorkflowDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workflow_id: EntityId) -> WorkflowDefinition | None:
        row = await self._session.get(WorkflowDefinitionOrmModel, workflow_id)
        return mappers.workflow_definition_to_domain(row) if row else None

    async def get_for_project(self, project_id: EntityId) -> WorkflowDefinition | None:
        stmt = select(WorkflowDefinitionOrmModel).where(WorkflowDefinitionOrmModel.project_id == project_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.workflow_definition_to_domain(row) if row else None

    async def add(self, workflow: WorkflowDefinition) -> None:
        self._session.add(mappers.workflow_definition_to_orm(workflow))

    async def update(self, workflow: WorkflowDefinition) -> None:
        row = await self._session.get(WorkflowDefinitionOrmModel, workflow.id)
        if row is None:
            raise ValueError(f"WorkflowDefinition {workflow.id} not found for update")
        if row.version != workflow.version:
            raise ConcurrencyConflictError("WorkflowDefinition", workflow.id)
        mappers.workflow_definition_to_orm(workflow, row)
        row.version = workflow.version + 1
        workflow.version += 1


class SqlAlchemyTasksAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: TasksAuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: TasksAuditEventCategory | None = None, limit: int = 50
    ) -> list[TasksAuditLogRecord]:
        stmt = select(TasksAuditLogOrmModel).where(TasksAuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(TasksAuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(TasksAuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
