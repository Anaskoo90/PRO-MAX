"""Tasks & Work Management domain events — in-process only, mirroring the
shape/conventions of app.identity.domain.events and app.projects.domain.events."""

from __future__ import annotations

from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class TaskCreated(DomainEvent):
    event_type = "tasks.task_created"
    project_id: UUID
    org_id: UUID
    title: str


class TaskDuplicated(DomainEvent):
    event_type = "tasks.task_duplicated"
    project_id: UUID
    org_id: UUID
    source_task_id: UUID


class TaskUpdated(DomainEvent):
    event_type = "tasks.task_updated"


class TaskStatusChanged(DomainEvent):
    event_type = "tasks.task_status_changed"
    from_status: str
    to_status: str


class TaskPriorityChanged(DomainEvent):
    event_type = "tasks.task_priority_changed"
    priority: str


class TaskDatesChanged(DomainEvent):
    event_type = "tasks.task_dates_changed"


class TaskReordered(DomainEvent):
    event_type = "tasks.task_reordered"
    position: float


class TaskParentChanged(DomainEvent):
    event_type = "tasks.task_parent_changed"
    parent_task_id: UUID | None = None


class TaskArchived(DomainEvent):
    event_type = "tasks.task_archived"


class TaskRestored(DomainEvent):
    event_type = "tasks.task_restored"


class TaskDeleted(DomainEvent):
    event_type = "tasks.task_deleted"


class TaskBecameOverdue(DomainEvent):
    """Not raised by the aggregate itself (overdue-ness is a function of
    time, not a state transition) — raised by the scheduled overdue-scan
    job (application layer) the first time a task is observed past due."""

    event_type = "tasks.task_became_overdue"


class TaskAssigned(DomainEvent):
    event_type = "tasks.task_assigned"
    user_id: UUID
    is_primary: bool


class TaskUnassigned(DomainEvent):
    event_type = "tasks.task_unassigned"
    user_id: UUID


class TaskReassigned(DomainEvent):
    event_type = "tasks.task_reassigned"
    previous_user_id: UUID | None = None
    new_user_id: UUID


class LabelCreated(DomainEvent):
    event_type = "tasks.label_created"
    project_id: UUID
    name: str


class LabelUpdated(DomainEvent):
    event_type = "tasks.label_updated"


class LabelDeleted(DomainEvent):
    event_type = "tasks.label_deleted"


class TaskLabelAttached(DomainEvent):
    event_type = "tasks.task_label_attached"
    label_id: UUID


class TaskLabelDetached(DomainEvent):
    event_type = "tasks.task_label_detached"
    label_id: UUID


class TaskDependencyAdded(DomainEvent):
    event_type = "tasks.task_dependency_added"
    depends_on_task_id: UUID


class TaskDependencyRemoved(DomainEvent):
    event_type = "tasks.task_dependency_removed"
    depends_on_task_id: UUID


class TaskRelationAdded(DomainEvent):
    event_type = "tasks.task_relation_added"
    related_task_id: UUID


class TaskRelationRemoved(DomainEvent):
    event_type = "tasks.task_relation_removed"
    related_task_id: UUID


class WorkflowDefinitionCreated(DomainEvent):
    event_type = "tasks.workflow_definition_created"
    project_id: UUID
    name: str


class WorkflowDefinitionUpdated(DomainEvent):
    event_type = "tasks.workflow_definition_updated"
