"""projects initial schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS projects")

    op.create_table(
        "workspaces",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "slug", name="uq_workspaces_org_slug"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_workspaces_status"),
        schema="projects",
    )
    op.create_index("ix_workspaces_org_id", "workspaces", ["org_id"], schema="projects")

    op.create_table(
        "workspace_memberships",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.workspaces.id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"),
        sa.CheckConstraint("role IN ('owner','admin','member','viewer')", name="ck_workspace_memberships_role"),
        schema="projects",
    )
    op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"], schema="projects")

    op.create_table(
        "project_templates",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_status", sa.String(), nullable=False, server_default="planning"),
        sa.Column("default_visibility", sa.String(), nullable=False, server_default="workspace"),
        sa.Column("default_metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("default_settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "default_status IN ('planning','active','on_hold','completed','archived')",
            name="ck_project_templates_default_status",
        ),
        sa.CheckConstraint(
            "default_visibility IN ('private','workspace','organization')",
            name="ck_project_templates_default_visibility",
        ),
        schema="projects",
    )
    op.create_index("ix_project_templates_org_id", "project_templates", ["org_id"], schema="projects")

    op.create_table(
        "projects_table",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.workspaces.id"), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="planning"),
        sa.Column("visibility", sa.String(), nullable=False, server_default="workspace"),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("template_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.project_templates.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('planning','active','on_hold','completed','archived')", name="ck_projects_status"
        ),
        sa.CheckConstraint("visibility IN ('private','workspace','organization')", name="ck_projects_visibility"),
        schema="projects",
    )
    op.create_index("ix_projects_workspace_id", "projects_table", ["workspace_id"], schema="projects")
    op.create_index("ix_projects_org_id_status", "projects_table", ["org_id", "status"], schema="projects")

    op.create_table(
        "project_memberships",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.projects_table.id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="contributor"),
        sa.Column("status", sa.String(), nullable=False, server_default="invited"),
        sa.Column("invited_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("invited_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
        sa.CheckConstraint("role IN ('owner','admin','contributor','viewer')", name="ck_project_memberships_role"),
        sa.CheckConstraint("status IN ('invited','active')", name="ck_project_memberships_status"),
        schema="projects",
    )
    op.create_index("ix_project_memberships_user_id", "project_memberships", ["user_id"], schema="projects")

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('workspace_change','project_change','membership_change','template_change')",
            name="ck_projects_audit_logs_category",
        ),
        schema="projects",
    )
    op.create_index("ix_projects_audit_logs_org_id_occurred_at", "audit_logs", ["org_id", "occurred_at"], schema="projects")
    op.create_index("ix_projects_audit_logs_category", "audit_logs", ["category"], schema="projects")

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="projects",
    )
    op.create_index("ix_projects_outbox_messages_published_at", "outbox_messages", ["published_at"], schema="projects")


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="projects")
    op.drop_table("audit_logs", schema="projects")
    op.drop_table("project_memberships", schema="projects")
    op.drop_table("projects_table", schema="projects")
    op.drop_table("project_templates", schema="projects")
    op.drop_table("workspace_memberships", schema="projects")
    op.drop_table("workspaces", schema="projects")
    op.execute("DROP SCHEMA IF EXISTS projects CASCADE")
