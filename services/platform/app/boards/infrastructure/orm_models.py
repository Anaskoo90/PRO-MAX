"""SQLAlchemy ORM models for the `boards` schema — infrastructure-layer
only, per ADR-005..009 (domain layer never imports this module)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_BOARD_TYPE_CHECK = "board_type IN ('kanban','scrum','custom')"
_BOARD_STATUS_CHECK = "status IN ('active','archived')"
_SWIMLANE_STRATEGY_CHECK = "swimlane_strategy IN ('none','assignee','priority','label','project','epic','custom')"
_SPRINT_STATUS_CHECK = "status IN ('planned','active','completed','cancelled')"
_ESTIMATE_TYPE_CHECK = "estimate_type IN ('story_points','hours','custom')"


class BoardsBase(DeclarativeBase):
    pass


class BoardOrmModel(BoardsBase):
    __tablename__ = "boards_table"  # avoid clashing with the schema name "boards"
    __table_args__ = (
        Index("ix_boards_project_id", "project_id"),
        CheckConstraint(_BOARD_TYPE_CHECK, name="ck_boards_board_type"),
        CheckConstraint(_BOARD_STATUS_CHECK, name="ck_boards_status"),
        CheckConstraint(_SWIMLANE_STRATEGY_CHECK, name="ck_boards_swimlane_strategy"),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    # Cross-schema references to projects.projects_table / identity.organizations
    # — not hard FKs, per the platform's standing rule for cross-context refs.
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    board_type: Mapped[str] = mapped_column(String, nullable=False, default="kanban")
    swimlane_strategy: Mapped[str] = mapped_column(String, nullable=False, default="none")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class BoardColumnOrmModel(BoardsBase):
    __tablename__ = "board_columns"
    __table_args__ = (
        UniqueConstraint("board_id", "name", name="uq_board_columns_board_name"),
        Index("ix_board_columns_board_id", "board_id"),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    board_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.boards_table.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wip_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color: Mapped[str] = mapped_column(String, nullable=False, default="#94A3B8")
    mapped_task_status: Mapped[str | None] = mapped_column(String, nullable=True)
    policies: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SwimlaneOrmModel(BoardsBase):
    __tablename__ = "swimlanes"
    __table_args__ = (
        Index("ix_swimlanes_board_id", "board_id"),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    board_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.boards_table.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BoardCardOrmModel(BoardsBase):
    """Hard-deletable — removing a task from a board deletes its placement
    record, not the underlying task (owned by the frozen Tasks context)."""

    __tablename__ = "board_cards"
    __table_args__ = (
        UniqueConstraint("board_id", "task_id", name="uq_board_cards_board_task"),
        Index("ix_board_cards_column_id", "column_id"),
        Index("ix_board_cards_sprint_id", "sprint_id"),
        Index("ix_board_cards_task_id", "task_id"),
        CheckConstraint(
            f"estimate_type IS NULL OR ({_ESTIMATE_TYPE_CHECK})", name="ck_board_cards_estimate_type"
        ),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    board_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.boards_table.id"), nullable=False)
    # Cross-schema reference to tasks.tasks_table — not a hard FK.
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    column_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.board_columns.id"), nullable=True)
    swimlane_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.swimlanes.id"), nullable=True)
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.sprints.id"), nullable=True)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimate_type: Mapped[str | None] = mapped_column(String, nullable=True)
    estimate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_estimate_label: Mapped[str | None] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class SprintOrmModel(BoardsBase):
    __tablename__ = "sprints"
    __table_args__ = (
        Index("ix_sprints_board_id", "board_id"),
        CheckConstraint(_SPRINT_STATUS_CHECK, name="ck_sprints_status"),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    board_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.boards_table.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class SprintBurndownSnapshotOrmModel(BoardsBase):
    """Append-only — no update/delete in the repository."""

    __tablename__ = "sprint_burndown_snapshots"
    __table_args__ = (
        UniqueConstraint("sprint_id", "snapshot_date", name="uq_sprint_burndown_sprint_date"),
        Index("ix_sprint_burndown_sprint_id", "sprint_id"),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    sprint_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boards.sprints.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(nullable=False)
    remaining_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    remaining_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class BoardsAuditLogOrmModel(BoardsBase):
    """Append-only — no deleted_at, no update/delete in the repository."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_boards_audit_logs_org_id_occurred_at", "org_id", "occurred_at"),
        Index("ix_boards_audit_logs_category", "category"),
        CheckConstraint(
            "category IN ('board_change','column_change','card_change','sprint_change')",
            name="ck_boards_audit_logs_category",
        ),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
