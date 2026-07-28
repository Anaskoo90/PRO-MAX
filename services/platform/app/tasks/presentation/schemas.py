"""Request/response schemas for the Tasks & Work Management API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    priority: str = "medium"
    parent_task_id: UUID | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None
    reminder_date: datetime | None = None


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None


class DuplicateTaskRequest(BaseModel):
    title: str | None = None


class ChangeTaskStatusRequest(BaseModel):
    status: str


class ChangeTaskPriorityRequest(BaseModel):
    priority: str


class SetTaskDatesRequest(BaseModel):
    start_date: datetime | None = None
    due_date: datetime | None = None
    reminder_date: datetime | None = None


class SetTaskParentRequest(BaseModel):
    parent_task_id: UUID | None = None


class MoveTaskRequest(BaseModel):
    previous_task_id: UUID | None = None
    next_task_id: UUID | None = None


class TaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    org_id: UUID
    title: str
    description: str
    status: str
    priority: str
    parent_task_id: UUID | None
    position: float
    start_date: datetime | None
    due_date: datetime | None
    reminder_date: datetime | None
    completion_date: datetime | None
    is_archived: bool
    archived_at: datetime | None
    is_overdue: bool


class TaskSearchRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    label_id: UUID | None = None
    assignee_user_id: UUID | None = None
    search_text: str | None = None
    include_archived: bool = False
    parent_task_id: UUID | None = None


class AssignTaskRequest(BaseModel):
    assignee_user_id: UUID
    is_primary: bool = False


class ReassignTaskRequest(BaseModel):
    from_user_id: UUID | None = None
    to_user_id: UUID


class TaskAssignmentResponse(BaseModel):
    id: UUID
    task_id: UUID
    user_id: UUID
    assigned_by: UUID
    is_primary: bool
    assigned_at: datetime


class TaskAssignmentHistoryResponse(BaseModel):
    id: UUID
    task_id: UUID
    user_id: UUID
    action: str
    actor_user_id: UUID
    occurred_at: datetime


class CreateLabelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class UpdateLabelRequest(BaseModel):
    name: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class LabelResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    color: str


class AddDependencyRequest(BaseModel):
    depends_on_task_id: UUID


class TaskDependencyResponse(BaseModel):
    id: UUID
    task_id: UUID
    depends_on_task_id: UUID


class AddRelatedTaskRequest(BaseModel):
    related_task_id: UUID


class TaskRelationResponse(BaseModel):
    id: UUID
    task_id: UUID
    related_task_id: UUID


class CreateWorkflowDefinitionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    statuses: list[str]
    transitions: dict[str, list[str]]


class WorkflowDefinitionResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    statuses: list[str]
    transitions: dict[str, list[str]]
