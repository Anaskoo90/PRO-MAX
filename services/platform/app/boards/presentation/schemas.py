"""Request/response schemas for the Boards & Agile Management API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateBoardRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    board_type: str = "kanban"
    swimlane_strategy: str = "none"


class UpdateBoardRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class UpdateBoardSettingsRequest(BaseModel):
    patch: dict[str, Any]


class ChangeSwimlaneStrategyRequest(BaseModel):
    strategy: str


class BoardResponse(BaseModel):
    id: UUID
    project_id: UUID
    org_id: UUID
    name: str
    description: str
    board_type: str
    swimlane_strategy: str
    status: str
    settings: dict[str, Any]
    archived_at: datetime | None


class CreateColumnRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    wip_limit: int | None = None
    color: str = Field(default="#94A3B8", pattern=r"^#[0-9A-Fa-f]{6}$")
    mapped_task_status: str | None = None


class RenameColumnRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SetWipLimitRequest(BaseModel):
    wip_limit: int | None = None


class SetColumnColorRequest(BaseModel):
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class SetColumnPoliciesRequest(BaseModel):
    policies: dict[str, Any]


class SetMappedTaskStatusRequest(BaseModel):
    status: str | None = None


class ReorderColumnRequest(BaseModel):
    previous_column_id: UUID | None = None
    next_column_id: UUID | None = None


class BoardColumnResponse(BaseModel):
    id: UUID
    board_id: UUID
    name: str
    position: float
    wip_limit: int | None
    color: str
    mapped_task_status: str | None
    policies: dict[str, Any]
    card_count: int


class CreateSwimlaneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RenameSwimlaneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ReorderSwimlaneRequest(BaseModel):
    previous_swimlane_id: UUID | None = None
    next_swimlane_id: UUID | None = None


class SwimlaneResponse(BaseModel):
    id: UUID
    board_id: UUID
    name: str
    position: float


class SwimlaneGroupResponse(BaseModel):
    key: str
    label: str
    card_ids: list[UUID]


class AddTaskToBoardRequest(BaseModel):
    task_id: UUID
    column_id: UUID | None = None


class MoveTaskToColumnRequest(BaseModel):
    column_id: UUID | None = None
    previous_card_id: UUID | None = None
    next_card_id: UUID | None = None
    swimlane_id: UUID | None = None


class ReorderTaskRequest(BaseModel):
    previous_card_id: UUID | None = None
    next_card_id: UUID | None = None


class BatchMoveEntry(BaseModel):
    card_id: UUID
    column_id: UUID | None = None


class BatchMoveRequest(BaseModel):
    moves: list[BatchMoveEntry]


class SetEstimateRequest(BaseModel):
    estimate_type: str
    value: float
    custom_label: str | None = None


class AssignToSprintRequest(BaseModel):
    sprint_id: UUID


class BoardCardResponse(BaseModel):
    id: UUID
    board_id: UUID
    task_id: UUID
    column_id: UUID | None
    swimlane_id: UUID | None
    sprint_id: UUID | None
    position: float
    estimate_type: str | None
    estimate_value: float | None
    custom_estimate_label: str | None


class CreateSprintRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = ""
    start_date: date | None = None
    end_date: date | None = None
    capacity: float | None = None


class UpdateSprintRequest(BaseModel):
    name: str | None = None
    goal: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    capacity: float | None = None


class SprintResponse(BaseModel):
    id: UUID
    board_id: UUID
    name: str
    goal: str
    status: str
    start_date: date | None
    end_date: date | None
    capacity: float | None


class SprintVelocityResponse(BaseModel):
    sprint_id: UUID
    velocity: float


class BurndownSnapshotResponse(BaseModel):
    snapshot_date: date
    remaining_points: float
    remaining_hours: float


class BurndownReportResponse(BaseModel):
    sprint_id: UUID
    capacity: float | None
    snapshots: list[BurndownSnapshotResponse]
    ideal_remaining_by_day: list[float]
