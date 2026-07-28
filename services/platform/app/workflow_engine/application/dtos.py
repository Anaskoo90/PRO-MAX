"""Application-layer DTOs for the Workflow Engine context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WorkflowDTO:
    id: UUID
    project_id: UUID
    org_id: UUID
    name: str
    description: str
    status: str
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkflowStateDTO:
    id: UUID
    workflow_id: UUID
    name: str
    position: float
    is_initial: bool
    is_final: bool
    is_hidden: bool
    is_archived: bool
    mapped_task_status: str | None


@dataclass(frozen=True, slots=True)
class WorkflowTransitionDTO:
    id: UUID
    workflow_id: UUID
    name: str
    from_state_id: UUID
    to_state_id: UUID
    position: float
    enabled: bool
    is_automatic: bool


@dataclass(frozen=True, slots=True)
class TransitionRuleDTO:
    id: UUID
    transition_id: UUID
    rule_type: str
    config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkflowActionDTO:
    id: UUID
    transition_id: UUID
    action_type: str
    config: dict[str, Any]
    position: float
    trigger_mode: str
    delay_seconds: float | None
    scheduled_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkflowConditionDTO:
    id: UUID
    transition_id: UUID
    condition_type: str
    operator: str
    value: Any
    position: float


@dataclass(frozen=True, slots=True)
class WorkflowTaskStateDTO:
    id: UUID
    workflow_id: UUID
    task_id: UUID
    current_state_id: UUID
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkflowExecutionRecordDTO:
    id: UUID
    workflow_id: UUID
    task_id: UUID
    transition_id: UUID
    from_state_id: UUID
    to_state_id: UUID
    actor_user_id: UUID
    reason: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class PendingAutomationActionDTO:
    id: UUID
    workflow_id: UUID
    task_id: UUID
    transition_id: UUID
    action_id: UUID
    run_at: datetime
    status: str
    executed_at: datetime | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class WorkflowApprovalRequestDTO:
    id: UUID
    transition_id: UUID
    task_id: UUID
    status: str
    requested_by: UUID
    requested_at: datetime
    decided_by: UUID | None
    decided_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class WorkflowChecklistItemDTO:
    id: UUID
    transition_id: UUID
    label: str
    position: float


@dataclass(frozen=True, slots=True)
class WorkflowActivityEntryDTO:
    id: UUID
    workflow_id: UUID
    task_id: UUID
    transition_id: UUID | None
    entry_type: str
    body: str
    actor_user_id: UUID
    occurred_at: datetime
