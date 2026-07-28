"""Workflow Engine domain events — in-process only, mirroring the
shape/conventions of every prior context's domain events exactly. One
class per workflow action, per submodule 9's requirement."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class WorkflowCreated(DomainEvent):
    event_type = "workflow_engine.workflow_created"
    project_id: UUID
    org_id: UUID
    name: str


class WorkflowUpdated(DomainEvent):
    event_type = "workflow_engine.workflow_updated"


class WorkflowArchived(DomainEvent):
    event_type = "workflow_engine.workflow_archived"


class WorkflowRestored(DomainEvent):
    event_type = "workflow_engine.workflow_restored"


class WorkflowDeleted(DomainEvent):
    event_type = "workflow_engine.workflow_deleted"


class StateCreated(DomainEvent):
    event_type = "workflow_engine.state_created"
    workflow_id: UUID
    name: str


class StateUpdated(DomainEvent):
    event_type = "workflow_engine.state_updated"


class StateDeleted(DomainEvent):
    event_type = "workflow_engine.state_deleted"


class TransitionCreated(DomainEvent):
    event_type = "workflow_engine.transition_created"
    workflow_id: UUID
    name: str


class TransitionRenamed(DomainEvent):
    event_type = "workflow_engine.transition_renamed"


class TransitionDeleted(DomainEvent):
    event_type = "workflow_engine.transition_deleted"


class TransitionEnabled(DomainEvent):
    event_type = "workflow_engine.transition_enabled"


class TransitionDisabled(DomainEvent):
    event_type = "workflow_engine.transition_disabled"


class TaskEnrolledInWorkflow(DomainEvent):
    event_type = "workflow_engine.task_enrolled"
    workflow_id: UUID
    task_id: UUID
    state_id: UUID


class TransitionExecuted(DomainEvent):
    event_type = "workflow_engine.transition_executed"
    workflow_id: UUID
    task_id: UUID
    transition_id: UUID
    from_state_id: UUID
    to_state_id: UUID


class ActionExecuted(DomainEvent):
    event_type = "workflow_engine.action_executed"
    workflow_id: UUID
    task_id: UUID
    action_id: UUID
    action_type: str


class ActionScheduled(DomainEvent):
    event_type = "workflow_engine.action_scheduled"
    workflow_id: UUID
    task_id: UUID
    action_id: UUID
    run_at: datetime


class ActionExecutionFailed(DomainEvent):
    event_type = "workflow_engine.action_execution_failed"
    workflow_id: UUID
    task_id: UUID
    action_id: UUID
    reason: str


class ApprovalRequested(DomainEvent):
    event_type = "workflow_engine.approval_requested"
    transition_id: UUID
    task_id: UUID


class ApprovalDecided(DomainEvent):
    event_type = "workflow_engine.approval_decided"
    transition_id: UUID
    task_id: UUID
    decision: str


class ChecklistItemCompleted(DomainEvent):
    event_type = "workflow_engine.checklist_item_completed"
    transition_id: UUID
    task_id: UUID
    checklist_item_id: UUID
