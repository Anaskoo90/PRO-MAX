"""
Boards & Agile Management domain entities.

Board and Sprint are aggregate roots (EventRecordingMixin). Column,
Swimlane, and BoardCard are plain join/structural entities managed by
their own application services — same convention as every prior context
(events for these are constructed and dispatched at the application layer,
not recorded on the entity itself).

A BoardCard is this context's own placement record for a Task (from the
frozen Tasks & Work Management context) on a specific board — column_id
NULL means "in this board's backlog, not yet placed in a column". Estimates
live on BoardCard, not on Task, since estimation is an agile/board concern
Tasks was never scoped to hold.

Plain Python classes, not pydantic/SQLAlchemy models — same dependency
rule as every other context (ADR-005..009): domain depends only on
shared_kernel/events.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from app.boards.domain.events import (
    BoardArchived,
    BoardCreated,
    BoardDeleted,
    BoardRestored,
    BoardUpdated,
    ColumnCreated,
    ColumnDeleted,
    ColumnReordered,
    ColumnUpdated,
    SprintCancelled,
    SprintCompleted,
    SprintCreated,
    SprintStarted,
    SprintUpdated,
    SwimlaneCreated,
    SwimlaneDeleted,
    SwimlaneUpdated,
    TaskEstimateSet,
)
from app.boards.domain.exceptions import (
    BoardAlreadyArchivedError,
    BoardAlreadyDeletedError,
    BoardNotActiveError,
    BoardNotArchivedError,
    InvalidEstimateError,
    InvalidSprintDateRangeError,
    InvalidSprintTransitionError,
    InvalidWipLimitError,
)


class BoardType(StrEnum):
    KANBAN = "kanban"
    SCRUM = "scrum"
    CUSTOM = "custom"


class BoardStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SwimlaneStrategy(StrEnum):
    NONE = "none"
    ASSIGNEE = "assignee"
    PRIORITY = "priority"
    LABEL = "label"
    PROJECT = "project"
    EPIC = "epic"
    CUSTOM = "custom"


class EstimateType(StrEnum):
    STORY_POINTS = "story_points"
    HOURS = "hours"
    CUSTOM = "custom"


class SprintStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


_ALLOWED_SPRINT_TRANSITIONS: dict[SprintStatus, frozenset[SprintStatus]] = {
    SprintStatus.PLANNED: frozenset({SprintStatus.ACTIVE, SprintStatus.CANCELLED}),
    SprintStatus.ACTIVE: frozenset({SprintStatus.COMPLETED, SprintStatus.CANCELLED}),
    SprintStatus.COMPLETED: frozenset(),
    SprintStatus.CANCELLED: frozenset(),
}

_POSITION_GAP = 1024.0


def compute_position_between(previous: float | None, following: float | None) -> float:
    """Fractional indexing — identical technique to Tasks' compute_position_between,
    reimplemented here (not imported) since domain layers never depend on
    another bounded context, even for a small pure function."""
    if previous is None and following is None:
        return _POSITION_GAP
    if previous is None:
        return following - _POSITION_GAP  # type: ignore[operator]
    if following is None:
        return previous + _POSITION_GAP
    return (previous + following) / 2


class Board(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        project_id: EntityId,
        org_id: OrgId,
        name: str,
        description: str,
        board_type: BoardType,
        swimlane_strategy: SwimlaneStrategy,
        status: BoardStatus,
        settings: dict[str, Any] | None = None,
        archived_at: datetime | None = None,
        deleted_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.project_id = project_id
        self.org_id = org_id
        self.name = name
        self.description = description
        self.board_type = board_type
        self.swimlane_strategy = swimlane_strategy
        self.status = status
        self.settings = settings or {}
        self.archived_at = archived_at
        self.deleted_at = deleted_at
        self.version = version

    @classmethod
    def create(
        cls, *, project_id: EntityId, org_id: OrgId, name: str, description: str = "",
        board_type: BoardType = BoardType.KANBAN, swimlane_strategy: SwimlaneStrategy = SwimlaneStrategy.NONE,
    ) -> "Board":
        board = cls(
            id=EntityId(new_uuid7()), project_id=project_id, org_id=org_id, name=name, description=description,
            board_type=board_type, swimlane_strategy=swimlane_strategy, status=BoardStatus.ACTIVE,
        )
        board.record_event(BoardCreated(aggregate_id=board.id, project_id=project_id, org_id=org_id, name=name, board_type=board_type.value))
        return board

    def assert_active(self) -> None:
        if self.status != BoardStatus.ACTIVE:
            raise BoardNotActiveError(self.status.value)

    def assert_not_deleted(self) -> None:
        if self.deleted_at is not None:
            raise BoardAlreadyDeletedError()

    def update(self, *, name: str | None = None, description: str | None = None) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        self.record_event(BoardUpdated(aggregate_id=self.id))

    def update_settings(self, patch: dict[str, Any]) -> None:
        self.settings = {**self.settings, **patch}
        self.record_event(BoardUpdated(aggregate_id=self.id))

    def change_swimlane_strategy(self, strategy: SwimlaneStrategy) -> None:
        self.swimlane_strategy = strategy
        self.record_event(BoardUpdated(aggregate_id=self.id))

    def archive(self) -> None:
        if self.status == BoardStatus.ARCHIVED:
            raise BoardAlreadyArchivedError()
        self.status = BoardStatus.ARCHIVED
        self.archived_at = utcnow()
        self.record_event(BoardArchived(aggregate_id=self.id))

    def restore(self) -> None:
        if self.status != BoardStatus.ARCHIVED:
            raise BoardNotArchivedError()
        self.status = BoardStatus.ACTIVE
        self.archived_at = None
        self.record_event(BoardRestored(aggregate_id=self.id))

    def mark_deleted(self) -> None:
        self.assert_not_deleted()
        self.deleted_at = utcnow()
        self.record_event(BoardDeleted(aggregate_id=self.id))


class BoardColumn:
    def __init__(
        self, *, id: EntityId, board_id: EntityId, name: str, position: float, wip_limit: int | None = None,
        color: str = "#94A3B8", mapped_task_status: str | None = None, policies: dict[str, Any] | None = None,
        version: int = 1,
    ) -> None:
        self.id = id
        self.board_id = board_id
        self.name = name
        self.position = position
        self.wip_limit = wip_limit
        self.color = color
        self.mapped_task_status = mapped_task_status
        self.policies = policies or {}
        self.version = version

    @classmethod
    def create(
        cls, *, board_id: EntityId, name: str, position: float, wip_limit: int | None = None,
        color: str = "#94A3B8", mapped_task_status: str | None = None,
    ) -> "BoardColumn":
        if wip_limit is not None and wip_limit <= 0:
            raise InvalidWipLimitError()
        return cls(id=EntityId(new_uuid7()), board_id=board_id, name=name, position=position, wip_limit=wip_limit, color=color, mapped_task_status=mapped_task_status)

    def rename(self, name: str) -> None:
        self.name = name

    def set_wip_limit(self, wip_limit: int | None) -> None:
        if wip_limit is not None and wip_limit <= 0:
            raise InvalidWipLimitError()
        self.wip_limit = wip_limit

    def set_color(self, color: str) -> None:
        self.color = color

    def set_policies(self, policies: dict[str, Any]) -> None:
        self.policies = {**self.policies, **policies}

    def set_mapped_task_status(self, status: str | None) -> None:
        self.mapped_task_status = status

    def set_position(self, position: float) -> None:
        self.position = position


class Swimlane:
    """Only meaningful when the owning Board's swimlane_strategy is CUSTOM —
    every other strategy computes its groups dynamically from Task data
    (see application/swimlane_management.py), not from stored rows."""

    def __init__(self, *, id: EntityId, board_id: EntityId, name: str, position: float, version: int = 1) -> None:
        self.id = id
        self.board_id = board_id
        self.name = name
        self.position = position
        self.version = version

    @classmethod
    def create(cls, *, board_id: EntityId, name: str, position: float) -> "Swimlane":
        return cls(id=EntityId(new_uuid7()), board_id=board_id, name=name, position=position)

    def rename(self, name: str) -> None:
        self.name = name

    def set_position(self, position: float) -> None:
        self.position = position


class BoardCard:
    def __init__(
        self, *, id: EntityId, board_id: EntityId, task_id: EntityId, column_id: EntityId | None = None,
        swimlane_id: EntityId | None = None, sprint_id: EntityId | None = None, position: float = 0.0,
        estimate_type: EstimateType | None = None, estimate_value: float | None = None,
        custom_estimate_label: str | None = None, added_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.board_id = board_id
        self.task_id = task_id
        self.column_id = column_id
        self.swimlane_id = swimlane_id
        self.sprint_id = sprint_id
        self.position = position
        self.estimate_type = estimate_type
        self.estimate_value = estimate_value
        self.custom_estimate_label = custom_estimate_label
        self.added_at = added_at or utcnow()

    @classmethod
    def add_to_board(
        cls, *, board_id: EntityId, task_id: EntityId, column_id: EntityId | None = None,
        swimlane_id: EntityId | None = None, position: float = _POSITION_GAP,
    ) -> "BoardCard":
        return cls(id=EntityId(new_uuid7()), board_id=board_id, task_id=task_id, column_id=column_id, swimlane_id=swimlane_id, position=position)

    def move_to_column(self, *, column_id: EntityId | None, position: float, swimlane_id: EntityId | None = None) -> None:
        self.column_id = column_id
        self.position = position
        if swimlane_id is not None or self.swimlane_id is not None:
            self.swimlane_id = swimlane_id

    def assign_to_sprint(self, sprint_id: EntityId) -> None:
        self.sprint_id = sprint_id

    def remove_from_sprint(self) -> None:
        self.sprint_id = None

    def set_estimate(self, *, estimate_type: EstimateType, value: float, custom_label: str | None = None) -> None:
        if value < 0:
            raise InvalidEstimateError("Estimate value must not be negative")
        if estimate_type == EstimateType.CUSTOM and not custom_label:
            raise InvalidEstimateError("A custom estimate requires a label")
        self.estimate_type = estimate_type
        self.estimate_value = value
        self.custom_estimate_label = custom_label

    def is_in_backlog(self) -> bool:
        return self.column_id is None


class Sprint(EventRecordingMixin):
    def __init__(
        self, *, id: EntityId, board_id: EntityId, name: str, goal: str, status: SprintStatus,
        start_date: date | None = None, end_date: date | None = None, capacity: float | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.board_id = board_id
        self.name = name
        self.goal = goal
        self.status = status
        self.start_date = start_date
        self.end_date = end_date
        self.capacity = capacity
        self.version = version

    @classmethod
    def create(
        cls, *, board_id: EntityId, name: str, goal: str = "", start_date: date | None = None,
        end_date: date | None = None, capacity: float | None = None,
    ) -> "Sprint":
        _assert_date_order(start_date, end_date)
        sprint = cls(
            id=EntityId(new_uuid7()), board_id=board_id, name=name, goal=goal, status=SprintStatus.PLANNED,
            start_date=start_date, end_date=end_date, capacity=capacity,
        )
        sprint.record_event(SprintCreated(aggregate_id=sprint.id, board_id=board_id, name=name))
        return sprint

    def update(
        self, *, name: str | None = None, goal: str | None = None, start_date: date | None = None,
        end_date: date | None = None, capacity: float | None = None,
    ) -> None:
        new_start = start_date if start_date is not None else self.start_date
        new_end = end_date if end_date is not None else self.end_date
        _assert_date_order(new_start, new_end)
        if name is not None:
            self.name = name
        if goal is not None:
            self.goal = goal
        self.start_date = new_start
        self.end_date = new_end
        if capacity is not None:
            self.capacity = capacity
        self.record_event(SprintUpdated(aggregate_id=self.id))

    def _transition(self, target: SprintStatus) -> None:
        allowed = _ALLOWED_SPRINT_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvalidSprintTransitionError(self.status.value, target.value)
        self.status = target

    def start(self) -> None:
        self._transition(SprintStatus.ACTIVE)
        self.record_event(SprintStarted(aggregate_id=self.id))

    def complete(self) -> None:
        self._transition(SprintStatus.COMPLETED)
        self.record_event(SprintCompleted(aggregate_id=self.id))

    def cancel(self) -> None:
        self._transition(SprintStatus.CANCELLED)
        self.record_event(SprintCancelled(aggregate_id=self.id))

    def is_active(self) -> bool:
        return self.status == SprintStatus.ACTIVE


def _assert_date_order(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise InvalidSprintDateRangeError("start_date must not be after end_date")


class SprintBurndownSnapshot:
    """Append-only — no update/delete, per the platform-wide convention for
    historical records. One row per (sprint, day), written by the daily
    burndown-scan job (see application/sprint_reporting.py + composition.py)."""

    def __init__(
        self, *, id: EntityId, sprint_id: EntityId, snapshot_date: date, remaining_points: float,
        remaining_hours: float, occurred_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.sprint_id = sprint_id
        self.snapshot_date = snapshot_date
        self.remaining_points = remaining_points
        self.remaining_hours = remaining_hours
        self.occurred_at = occurred_at or utcnow()

    @classmethod
    def create(
        cls, *, sprint_id: EntityId, snapshot_date: date, remaining_points: float, remaining_hours: float,
    ) -> "SprintBurndownSnapshot":
        return cls(id=EntityId(new_uuid7()), sprint_id=sprint_id, snapshot_date=snapshot_date, remaining_points=remaining_points, remaining_hours=remaining_hours)
