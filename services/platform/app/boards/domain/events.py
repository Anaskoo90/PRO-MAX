"""Boards & Agile Management domain events — in-process only, mirroring the
shape/conventions of every prior context's domain events exactly."""

from __future__ import annotations

from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class BoardCreated(DomainEvent):
    event_type = "boards.board_created"
    project_id: UUID
    org_id: UUID
    name: str
    board_type: str


class BoardUpdated(DomainEvent):
    event_type = "boards.board_updated"


class BoardArchived(DomainEvent):
    event_type = "boards.board_archived"


class BoardRestored(DomainEvent):
    event_type = "boards.board_restored"


class BoardDeleted(DomainEvent):
    event_type = "boards.board_deleted"


class ColumnCreated(DomainEvent):
    event_type = "boards.column_created"
    board_id: UUID
    name: str


class ColumnUpdated(DomainEvent):
    event_type = "boards.column_updated"


class ColumnReordered(DomainEvent):
    event_type = "boards.column_reordered"
    position: float


class ColumnDeleted(DomainEvent):
    event_type = "boards.column_deleted"


class SwimlaneCreated(DomainEvent):
    event_type = "boards.swimlane_created"
    board_id: UUID
    name: str


class SwimlaneUpdated(DomainEvent):
    event_type = "boards.swimlane_updated"


class SwimlaneDeleted(DomainEvent):
    event_type = "boards.swimlane_deleted"


class TaskAddedToBoard(DomainEvent):
    event_type = "boards.task_added_to_board"
    board_id: UUID
    task_id: UUID


class TaskRemovedFromBoard(DomainEvent):
    event_type = "boards.task_removed_from_board"
    board_id: UUID
    task_id: UUID


class TaskMoved(DomainEvent):
    event_type = "boards.task_moved"
    board_id: UUID
    task_id: UUID
    from_column_id: UUID | None = None
    to_column_id: UUID | None = None


class TaskEstimateSet(DomainEvent):
    event_type = "boards.task_estimate_set"
    estimate_type: str


class SprintCreated(DomainEvent):
    event_type = "boards.sprint_created"
    board_id: UUID
    name: str


class SprintUpdated(DomainEvent):
    event_type = "boards.sprint_updated"


class SprintStarted(DomainEvent):
    event_type = "boards.sprint_started"


class SprintCompleted(DomainEvent):
    event_type = "boards.sprint_completed"


class SprintCancelled(DomainEvent):
    event_type = "boards.sprint_cancelled"


class TaskAssignedToSprint(DomainEvent):
    event_type = "boards.task_assigned_to_sprint"
    sprint_id: UUID
    task_id: UUID


class TaskRemovedFromSprint(DomainEvent):
    event_type = "boards.task_removed_from_sprint"
    sprint_id: UUID
    task_id: UUID
