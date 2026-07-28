"""tasks initial schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_CHECK = "status IN ('backlog','todo','in_progress','review','testing','blocked','done','cancelled')"
_PRIORITY_CHECK = "priority IN ('low','medium','high','critical')"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS tasks")

    op.create_table(
        "tasks_table",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="backlog"),
        sa.Column("priority", sa.String(), nullable=False, server_default="medium"),
        sa.Column("parent_task_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("start_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("due_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reminder_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completion_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(_STATUS_CHECK, name="ck_tasks_status"),
        sa.CheckConstraint(_PRIORITY_CHECK, name="ck_tasks_priority"),
        schema="tasks",
    )
    # parent_task_id is self-referential; added after table creation so the
    # FK can point at a table that now exists.
    op.create_foreign_key(
        "fk_tasks_parent_task_id", "tasks_table", "tasks_table", ["parent_task_id"], ["id"],
        source_schema="tasks", referent_schema="tasks",
    )
    op.create_index("ix_tasks_project_id", "tasks_table", ["project_id"], schema="tasks")
    op.create_index("ix_tasks_project_id_status", "tasks_table", ["project_id", "status"], schema="tasks")
    op.create_index("ix_tasks_parent_task_id", "tasks_table", ["parent_task_id"], schema="tasks")
    op.create_index("ix_tasks_org_id_due_date", "tasks_table", ["org_id", "due_date"], schema="tasks")

    op.create_table(
        "task_assignments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_assignments_task_user"),
        schema="tasks",
    )
    op.create_index("ix_task_assignments_user_id", "task_assignments", ["user_id"], schema="tasks")

    op.create_table(
        "task_assignment_history",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("action IN ('assigned','unassigned','reassigned')", name="ck_task_assignment_history_action"),
        schema="tasks",
    )
    op.create_index("ix_task_assignment_history_task_id", "task_assignment_history", ["task_id"], schema="tasks")

    op.create_table(
        "labels",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("project_id", "name", name="uq_labels_project_name"),
        schema="tasks",
    )
    op.create_index("ix_labels_project_id", "labels", ["project_id"], schema="tasks")

    op.create_table(
        "task_labels",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("label_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.labels.id"), nullable=False),
        sa.UniqueConstraint("task_id", "label_id", name="uq_task_labels_task_label"),
        schema="tasks",
    )
    op.create_index("ix_task_labels_label_id", "task_labels", ["label_id"], schema="tasks")

    op.create_table(
        "task_dependencies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("depends_on_task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_task_dependson"),
        sa.CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependencies_not_self"),
        schema="tasks",
    )
    op.create_index("ix_task_dependencies_depends_on_task_id", "task_dependencies", ["depends_on_task_id"], schema="tasks")

    op.create_table(
        "task_relations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("related_task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.tasks_table.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "related_task_id", name="uq_task_relations_task_related"),
        sa.CheckConstraint("task_id <> related_task_id", name="ck_task_relations_not_self"),
        schema="tasks",
    )
    op.create_index("ix_task_relations_related_task_id", "task_relations", ["related_task_id"], schema="tasks")

    op.create_table(
        "workflow_definitions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("statuses", pg.JSONB(), nullable=False),
        sa.Column("transitions", pg.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="tasks",
    )
    op.create_index("ix_workflow_definitions_project_id", "workflow_definitions", ["project_id"], schema="tasks")

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
            "category IN ('task_change','assignment_change','label_change','relationship_change','workflow_change')",
            name="ck_tasks_audit_logs_category",
        ),
        schema="tasks",
    )
    op.create_index("ix_tasks_audit_logs_org_id_occurred_at", "audit_logs", ["org_id", "occurred_at"], schema="tasks")
    op.create_index("ix_tasks_audit_logs_category", "audit_logs", ["category"], schema="tasks")

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="tasks",
    )
    op.create_index("ix_tasks_outbox_messages_published_at", "outbox_messages", ["published_at"], schema="tasks")


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="tasks")
    op.drop_table("audit_logs", schema="tasks")
    op.drop_table("workflow_definitions", schema="tasks")
    op.drop_table("task_relations", schema="tasks")
    op.drop_table("task_dependencies", schema="tasks")
    op.drop_table("task_labels", schema="tasks")
    op.drop_table("labels", schema="tasks")
    op.drop_table("task_assignment_history", schema="tasks")
    op.drop_table("task_assignments", schema="tasks")
    op.drop_constraint("fk_tasks_parent_task_id", "tasks_table", schema="tasks", type_="foreignkey")
    op.drop_table("tasks_table", schema="tasks")
    op.execute("DROP SCHEMA IF EXISTS tasks CASCADE")
