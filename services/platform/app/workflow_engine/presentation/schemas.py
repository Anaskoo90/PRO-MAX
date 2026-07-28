"""Request/response schemas for the Workflow Engine API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateWorkflowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class WorkflowResponse(BaseModel):
    id: UUID
    project_id: UUID
    org_id: UUID
    name: str
    description: str
    status: str
    archived_at: datetime | None


class CreateStateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_initial: bool = False
    is_final: bool = False
    is_hidden: bool = False
    mapped_task_status: str | None = None


class RenameStateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SetStateFlagRequest(BaseModel):
    value: bool


class SetMappedTaskStatusRequest(BaseModel):
    status: str | None = None


class ReorderStateRequest(BaseModel):
    previous_state_id: UUID | None = None
    next_state_id: UUID | None = None


class WorkflowStateResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    name: str
    position: float
    is_initial: bool
    is_final: bool
    is_hidden: bool
    is_archived: bool
    mapped_task_status: str | None


class CreateTransitionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    from_state_id: UUID
    to_state_id: UUID
    is_automatic: bool = False


class RenameTransitionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SetAutomaticRequest(BaseModel):
    is_automatic: bool


class WorkflowTransitionResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    name: str
    from_state_id: UUID
    to_state_id: UUID
    position: float
    enabled: bool
    is_automatic: bool


class AddRuleRequest(BaseModel):
    rule_type: str
    config: dict[str, Any] = {}


class TransitionRuleResponse(BaseModel):
    id: UUID
    transition_id: UUID
    rule_type: str
    config: dict[str, Any]


class AddActionRequest(BaseModel):
    action_type: str
    config: dict[str, Any] = {}
    trigger_mode: str = "immediate"
    delay_seconds: float | None = None
    scheduled_at: datetime | None = None


class WorkflowActionResponse(BaseModel):
    id: UUID
    transition_id: UUID
    action_type: str
    config: dict[str, Any]
    position: float
    trigger_mode: str
    delay_seconds: float | None
    scheduled_at: datetime | None


class AddConditionRequest(BaseModel):
    condition_type: str
    operator: str
    value: Any = None


class WorkflowConditionResponse(BaseModel):
    id: UUID
    transition_id: UUID
    condition_type: str
    operator: str
    value: Any
    position: float


class AddChecklistItemRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)


class WorkflowChecklistItemResponse(BaseModel):
    id: UUID
    transition_id: UUID
    label: str
    position: float


class EnrollTaskRequest(BaseModel):
    task_id: UUID


class WorkflowTaskStateResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    task_id: UUID
    current_state_id: UUID
    updated_at: datetime


class ExecuteTransitionRequest(BaseModel):
    transition_id: UUID
    reason: str = ""


class WorkflowExecutionRecordResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    task_id: UUID
    transition_id: UUID
    from_state_id: UUID
    to_state_id: UUID
    actor_user_id: UUID
    reason: str
    occurred_at: datetime


class RequestApprovalRequest(BaseModel):
    task_id: UUID


class DecideApprovalRequest(BaseModel):
    approved: bool
    reason: str = ""


class WorkflowApprovalRequestResponse(BaseModel):
    id: UUID
    transition_id: UUID
    task_id: UUID
    status: str
    requested_by: UUID
    requested_at: datetime
    decided_by: UUID | None
    decided_at: datetime | None
    reason: str


class CompleteChecklistItemRequest(BaseModel):
    task_id: UUID
