"""ORM row <-> domain entity mapping for the Tasks & Work Management context."""

from __future__ import annotations

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
from app.tasks.domain.workflow import TaskPriority, TaskStatus, WorkflowDefinition
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
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def task_to_domain(row: TaskOrmModel) -> Task:
    return Task(
        id=EntityId(row.id), project_id=EntityId(row.project_id), org_id=OrgId(row.org_id), title=row.title,
        description=row.description, status=TaskStatus(row.status), priority=TaskPriority(row.priority),
        parent_task_id=EntityId(row.parent_task_id) if row.parent_task_id else None, position=row.position,
        start_date=row.start_date, due_date=row.due_date, reminder_date=row.reminder_date,
        completion_date=row.completion_date, is_archived=row.is_archived, archived_at=row.archived_at,
        deleted_at=row.deleted_at, version=row.version,
    )


def task_to_orm(entity: Task, row: TaskOrmModel | None = None) -> TaskOrmModel:
    row = row or TaskOrmModel(id=entity.id)
    row.project_id = entity.project_id
    row.org_id = entity.org_id
    row.title = entity.title
    row.description = entity.description
    row.status = entity.status.value
    row.priority = entity.priority.value
    row.parent_task_id = entity.parent_task_id
    row.position = entity.position
    row.start_date = entity.start_date
    row.due_date = entity.due_date
    row.reminder_date = entity.reminder_date
    row.completion_date = entity.completion_date
    row.is_archived = entity.is_archived
    row.archived_at = entity.archived_at
    row.deleted_at = entity.deleted_at
    row.version = entity.version
    return row


def task_assignment_to_domain(row: TaskAssignmentOrmModel) -> TaskAssignment:
    return TaskAssignment(
        id=EntityId(row.id), task_id=EntityId(row.task_id), user_id=UserId(row.user_id),
        assigned_by=UserId(row.assigned_by), is_primary=row.is_primary, assigned_at=row.assigned_at,
    )


def task_assignment_to_orm(entity: TaskAssignment) -> TaskAssignmentOrmModel:
    return TaskAssignmentOrmModel(
        id=entity.id, task_id=entity.task_id, user_id=entity.user_id, assigned_by=entity.assigned_by,
        is_primary=entity.is_primary,
    )


def task_assignment_history_to_domain(row: TaskAssignmentHistoryOrmModel) -> TaskAssignmentHistoryRecord:
    return TaskAssignmentHistoryRecord(
        id=EntityId(row.id), task_id=EntityId(row.task_id), user_id=UserId(row.user_id), action=row.action,
        actor_user_id=UserId(row.actor_user_id), occurred_at=row.occurred_at,
    )


def task_assignment_history_to_orm(entity: TaskAssignmentHistoryRecord) -> TaskAssignmentHistoryOrmModel:
    return TaskAssignmentHistoryOrmModel(
        id=entity.id, task_id=entity.task_id, user_id=entity.user_id, action=entity.action,
        actor_user_id=entity.actor_user_id,
    )


def label_to_domain(row: LabelOrmModel) -> Label:
    return Label(id=EntityId(row.id), project_id=EntityId(row.project_id), name=row.name, color=row.color, version=row.version)


def label_to_orm(entity: Label, row: LabelOrmModel | None = None) -> LabelOrmModel:
    row = row or LabelOrmModel(id=entity.id, project_id=entity.project_id)
    row.name = entity.name
    row.color = entity.color
    row.version = entity.version
    return row


def task_label_to_domain(row: TaskLabelOrmModel) -> TaskLabel:
    return TaskLabel(id=EntityId(row.id), task_id=EntityId(row.task_id), label_id=EntityId(row.label_id))


def task_label_to_orm(entity: TaskLabel) -> TaskLabelOrmModel:
    return TaskLabelOrmModel(id=entity.id, task_id=entity.task_id, label_id=entity.label_id)


def task_dependency_to_domain(row: TaskDependencyOrmModel) -> TaskDependency:
    return TaskDependency(
        id=EntityId(row.id), task_id=EntityId(row.task_id), depends_on_task_id=EntityId(row.depends_on_task_id),
        created_at=row.created_at,
    )


def task_dependency_to_orm(entity: TaskDependency) -> TaskDependencyOrmModel:
    return TaskDependencyOrmModel(id=entity.id, task_id=entity.task_id, depends_on_task_id=entity.depends_on_task_id)


def task_relation_to_domain(row: TaskRelationOrmModel) -> TaskRelation:
    return TaskRelation(
        id=EntityId(row.id), task_id=EntityId(row.task_id), related_task_id=EntityId(row.related_task_id),
        created_at=row.created_at,
    )


def task_relation_to_orm(entity: TaskRelation) -> TaskRelationOrmModel:
    return TaskRelationOrmModel(id=entity.id, task_id=entity.task_id, related_task_id=entity.related_task_id)


def workflow_definition_to_domain(row: WorkflowDefinitionOrmModel) -> WorkflowDefinition:
    statuses = tuple(TaskStatus(s) for s in row.statuses)
    transitions = {TaskStatus(k): frozenset(TaskStatus(v) for v in vs) for k, vs in row.transitions.items()}
    return WorkflowDefinition(
        id=EntityId(row.id), project_id=EntityId(row.project_id), name=row.name, statuses=statuses,
        transitions=transitions, version=row.version,
    )


def workflow_definition_to_orm(entity: WorkflowDefinition, row: WorkflowDefinitionOrmModel | None = None) -> WorkflowDefinitionOrmModel:
    row = row or WorkflowDefinitionOrmModel(id=entity.id, project_id=entity.project_id)
    row.name = entity.name
    row.statuses = [s.value for s in entity.statuses]
    row.transitions = {k.value: [v.value for v in vs] for k, vs in entity.transitions.items()}
    row.version = entity.version
    return row


def audit_log_to_domain(row: TasksAuditLogOrmModel) -> TasksAuditLogRecord:
    return TasksAuditLogRecord(
        id=EntityId(row.id), org_id=OrgId(row.org_id), category=TasksAuditEventCategory(row.category),
        action=row.action, actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type, resource_id=row.resource_id, metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: TasksAuditLogRecord) -> TasksAuditLogOrmModel:
    return TasksAuditLogOrmModel(
        id=entity.id, org_id=entity.org_id, category=entity.category.value, action=entity.action,
        actor_user_id=entity.actor_user_id, resource_type=entity.resource_type, resource_id=entity.resource_id,
        metadata_=entity.metadata, occurred_at=entity.occurred_at,
    )
