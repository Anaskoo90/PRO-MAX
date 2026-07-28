"""SQLAlchemy ORM models for the `tasks` schema — infrastructure-layer
only, per ADR-005..009 (domain layer never imports this module)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_STATUS_CHECK = "status IN ('backlog','todo','in_progress','review','testing','blocked','done','cancelled')"
_PRIORITY_CHECK = "priority IN ('low','medium','high','critical')"


class TasksBase(DeclarativeBase):
    pass


class TaskOrmModel(TasksBase):
    __tablename__ = "tasks_table"  # avoid clashing with the schema name "tasks"
    __table_args__ = (
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_project_id_status", "project_id", "status"),
        Index("ix_tasks_parent_task_id", "parent_task_id"),
        Index("ix_tasks_org_id_due_date", "org_id", "due_date"),
        CheckConstraint(_STATUS_CHECK, name="ck_tasks_status"),
        CheckConstraint(_PRIORITY_CHECK, name="ck_tasks_priority"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    # Cross-schema references to projects.projects_table / identity.organizations
    # — not hard FKs (bounded contexts don't share hard FKs across schemas,
    # per the platform's standing rule; enforced at the application layer
    # via ProjectContextPort / the Projects adapter instead).
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=True
    )
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_date: Mapped[datetime | None] = mapped_column(nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(nullable=True)
    reminder_date: Mapped[datetime | None] = mapped_column(nullable=True)
    completion_date: Mapped[datetime | None] = mapped_column(nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TaskAssignmentOrmModel(TasksBase):
    """Hard-deletable join table."""

    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_assignments_task_user"),
        Index("ix_task_assignments_user_id", "user_id"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class TaskAssignmentHistoryOrmModel(TasksBase):
    """Append-only — no update/delete in the repository."""

    __tablename__ = "task_assignment_history"
    __table_args__ = (
        Index("ix_task_assignment_history_task_id", "task_id"),
        CheckConstraint("action IN ('assigned','unassigned','reassigned')", name="ck_task_assignment_history_action"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class LabelOrmModel(TasksBase):
    __tablename__ = "labels"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_labels_project_name"),
        Index("ix_labels_project_id", "project_id"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TaskLabelOrmModel(TasksBase):
    """Hard-deletable join table."""

    __tablename__ = "task_labels"
    __table_args__ = (
        UniqueConstraint("task_id", "label_id", name="uq_task_labels_task_label"),
        Index("ix_task_labels_label_id", "label_id"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False)
    label_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.labels.id"), nullable=False)


class TaskDependencyOrmModel(TasksBase):
    """Hard-deletable join table. Directed: task_id depends on depends_on_task_id."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_task_dependson"),
        Index("ix_task_dependencies_depends_on_task_id", "depends_on_task_id"),
        CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependencies_not_self"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class TaskRelationOrmModel(TasksBase):
    """Hard-deletable join table. Symmetric relation, stored as one directed
    row per unordered pair (application layer enforces one canonical
    ordering to avoid duplicate reciprocal rows)."""

    __tablename__ = "task_relations"
    __table_args__ = (
        UniqueConstraint("task_id", "related_task_id", name="uq_task_relations_task_related"),
        Index("ix_task_relations_related_task_id", "related_task_id"),
        CheckConstraint("task_id <> related_task_id", name="ck_task_relations_not_self"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False)
    related_task_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.tasks_table.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class WorkflowDefinitionOrmModel(TasksBase):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        Index("ix_workflow_definitions_project_id", "project_id"),
        {"schema": "tasks"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    statuses: Mapped[list] = mapped_column(JSONB, nullable=False)
    transitions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class TasksAuditLogOrmModel(TasksBase):
    """Append-only — no deleted_at, no update/delete in the repository."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_tasks_audit_logs_org_id_occurred_at", "org_id", "occurred_at"),
        Index("ix_tasks_audit_logs_category", "category"),
        CheckConstraint(
            "category IN ('task_change','assignment_change','label_change','relationship_change','workflow_change')",
            name="ck_tasks_audit_logs_category",
        ),
        {"schema": "tasks"},
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
