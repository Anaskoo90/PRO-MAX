"""SQLAlchemy ORM models for the `projects` schema — infrastructure-layer
only, per ADR-005..009 (domain layer never imports this module)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProjectsBase(DeclarativeBase):
    pass


class WorkspaceOrmModel(ProjectsBase):
    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_workspaces_org_slug"),
        Index("ix_workspaces_org_id", "org_id"),
        CheckConstraint("status IN ('active','archived')", name="ck_workspaces_status"),
        {"schema": "projects"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    # Cross-schema reference to identity.organizations — not a hard FK
    # (bounded contexts don't share hard FKs across schemas, per the
    # platform's standing rule; enforced at the application layer via
    # OrgPermissionCheckerPort / the Identity adapter instead).
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkspaceMembershipOrmModel(ProjectsBase):
    """Hard-deletable join table — no deleted_at, per platform convention."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"),
        Index("ix_workspace_memberships_user_id", "user_id"),
        CheckConstraint("role IN ('owner','admin','member','viewer')", name="ck_workspace_memberships_role"),
        {"schema": "projects"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.workspaces.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class ProjectOrmModel(ProjectsBase):
    __tablename__ = "projects_table"  # avoid clashing with the schema name "projects" in generated SQL tooling
    __table_args__ = (
        Index("ix_projects_workspace_id", "workspace_id"),
        Index("ix_projects_org_id_status", "org_id", "status"),
        CheckConstraint(
            "status IN ('planning','active','on_hold','completed','archived')", name="ck_projects_status"
        ),
        CheckConstraint("visibility IN ('private','workspace','organization')", name="ck_projects_visibility"),
        {"schema": "projects"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.workspaces.id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="planning")
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="workspace")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.project_templates.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ProjectMembershipOrmModel(ProjectsBase):
    """Hard-deletable join table."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
        Index("ix_project_memberships_user_id", "user_id"),
        CheckConstraint("role IN ('owner','admin','contributor','viewer')", name="ck_project_memberships_role"),
        CheckConstraint("status IN ('invited','active')", name="ck_project_memberships_status"),
        {"schema": "projects"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.projects_table.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="contributor")
    status: Mapped[str] = mapped_column(String, nullable=False, default="invited")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    invited_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    joined_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ProjectTemplateOrmModel(ProjectsBase):
    __tablename__ = "project_templates"
    __table_args__ = (
        Index("ix_project_templates_org_id", "org_id"),
        CheckConstraint(
            "default_status IN ('planning','active','on_hold','completed','archived')",
            name="ck_project_templates_default_status",
        ),
        CheckConstraint(
            "default_visibility IN ('private','workspace','organization')",
            name="ck_project_templates_default_visibility",
        ),
        {"schema": "projects"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_status: Mapped[str] = mapped_column(String, nullable=False, default="planning")
    default_visibility: Mapped[str] = mapped_column(String, nullable=False, default="workspace")
    default_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ProjectsAuditLogOrmModel(ProjectsBase):
    """Append-only — no deleted_at, no update/delete in the repository."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_projects_audit_logs_org_id_occurred_at", "org_id", "occurred_at"),
        Index("ix_projects_audit_logs_category", "category"),
        CheckConstraint(
            "category IN ('workspace_change','project_change','membership_change','template_change')",
            name="ck_projects_audit_logs_category",
        ),
        {"schema": "projects"},
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
