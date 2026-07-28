"""Application-layer DTOs for the Boards & Agile Management context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BoardDTO:
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


@dataclass(frozen=True, slots=True)
class BoardColumnDTO:
    id: UUID
    board_id: UUID
    name: str
    position: float
    wip_limit: int | None
    color: str
    mapped_task_status: str | None
    policies: dict[str, Any]
    card_count: int = 0


@dataclass(frozen=True, slots=True)
class SwimlaneDTO:
    id: UUID
    board_id: UUID
    name: str
    position: float


@dataclass(frozen=True, slots=True)
class BoardCardDTO:
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


@dataclass(frozen=True, slots=True)
class SprintDTO:
    id: UUID
    board_id: UUID
    name: str
    goal: str
    status: str
    start_date: date | None
    end_date: date | None
    capacity: float | None


@dataclass(frozen=True, slots=True)
class BurndownSnapshotDTO:
    snapshot_date: date
    remaining_points: float
    remaining_hours: float


@dataclass(frozen=True, slots=True)
class BurndownReportDTO:
    sprint_id: UUID
    capacity: float | None
    snapshots: list[BurndownSnapshotDTO]
    ideal_remaining_by_day: list[float]


@dataclass(frozen=True, slots=True)
class SwimlaneGroupDTO:
    """One computed group for non-CUSTOM swimlane strategies (ASSIGNEE,
    PRIORITY, LABEL, PROJECT, EPIC) — the grouping key + the card ids that
    belong to it. See swimlane_management.py's honest handling of EPIC,
    which has no backing concept anywhere in the platform yet."""

    key: str
    label: str
    card_ids: list[UUID]
