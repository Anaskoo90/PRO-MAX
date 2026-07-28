"""Application-layer DTOs for the Tasks & Work Management context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TaskDTO:
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


@dataclass(frozen=True, slots=True)
class TaskAssignmentDTO:
    id: UUID
    task_id: UUID
    user_id: UUID
    assigned_by: UUID
    is_primary: bool
    assigned_at: datetime


@dataclass(frozen=True, slots=True)
class TaskAssignmentHistoryDTO:
    id: UUID
    task_id: UUID
    user_id: UUID
    action: str
    actor_user_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class LabelDTO:
    id: UUID
    project_id: UUID
    name: str
    color: str


@dataclass(frozen=True, slots=True)
class TaskDependencyDTO:
    id: UUID
    task_id: UUID
    depends_on_task_id: UUID


@dataclass(frozen=True, slots=True)
class TaskRelationDTO:
    id: UUID
    task_id: UUID
    related_task_id: UUID


@dataclass(frozen=True, slots=True)
class WorkflowDefinitionDTO:
    id: UUID
    project_id: UUID
    name: str
    statuses: list[str]
    transitions: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class TaskListFilter:
    """A Query object (CQRS's read side) — distinct from the Commands
    TaskService's mutating methods accept, and expressive enough to cover
    Labels' "Filtering"/"Search" requirements without every combination
    needing its own repository method."""

    status: str | None = None
    priority: str | None = None
    label_id: UUID | None = None
    assignee_user_id: UUID | None = None
    search_text: str | None = None
    include_archived: bool = False
    parent_task_id: UUID | None = None
