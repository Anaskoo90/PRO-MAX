"""boards initial schema

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BOARD_TYPE_CHECK = "board_type IN ('kanban','scrum','custom')"
_BOARD_STATUS_CHECK = "status IN ('active','archived')"
_SWIMLANE_STRATEGY_CHECK = "swimlane_strategy IN ('none','assignee','priority','label','project','epic','custom')"
_SPRINT_STATUS_CHECK = "status IN ('planned','active','completed','cancelled')"
_ESTIMATE_TYPE_CHECK = "estimate_type IN ('story_points','hours','custom')"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS boards")

    op.create_table(
        "boards_table",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("board_type", sa.String(), nullable=False, server_default="kanban"),
        sa.Column("swimlane_strategy", sa.String(), nullable=False, server_default="none"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(_BOARD_TYPE_CHECK, name="ck_boards_board_type"),
        sa.CheckConstraint(_BOARD_STATUS_CHECK, name="ck_boards_status"),
        sa.CheckConstraint(_SWIMLANE_STRATEGY_CHECK, name="ck_boards_swimlane_strategy"),
        schema="boards",
    )
    op.create_index("ix_boards_project_id", "boards_table", ["project_id"], schema="boards")

    op.create_table(
        "board_columns",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("board_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.boards_table.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("wip_limit", sa.Integer(), nullable=True),
        sa.Column("color", sa.String(), nullable=False, server_default="#94A3B8"),
        sa.Column("mapped_task_status", sa.String(), nullable=True),
        sa.Column("policies", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("board_id", "name", name="uq_board_columns_board_name"),
        schema="boards",
    )
    op.create_index("ix_board_columns_board_id", "board_columns", ["board_id"], schema="boards")

    op.create_table(
        "swimlanes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("board_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.boards_table.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="boards",
    )
    op.create_index("ix_swimlanes_board_id", "swimlanes", ["board_id"], schema="boards")

    op.create_table(
        "sprints",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("board_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.boards_table.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("capacity", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(_SPRINT_STATUS_CHECK, name="ck_sprints_status"),
        schema="boards",
    )
    op.create_index("ix_sprints_board_id", "sprints", ["board_id"], schema="boards")

    op.create_table(
        "board_cards",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("board_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.boards_table.id"), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("column_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.board_columns.id"), nullable=True),
        sa.Column("swimlane_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.swimlanes.id"), nullable=True),
        sa.Column("sprint_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.sprints.id"), nullable=True),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("estimate_type", sa.String(), nullable=True),
        sa.Column("estimate_value", sa.Float(), nullable=True),
        sa.Column("custom_estimate_label", sa.String(), nullable=True),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("board_id", "task_id", name="uq_board_cards_board_task"),
        sa.CheckConstraint(f"estimate_type IS NULL OR ({_ESTIMATE_TYPE_CHECK})", name="ck_board_cards_estimate_type"),
        schema="boards",
    )
    op.create_index("ix_board_cards_column_id", "board_cards", ["column_id"], schema="boards")
    op.create_index("ix_board_cards_sprint_id", "board_cards", ["sprint_id"], schema="boards")
    op.create_index("ix_board_cards_task_id", "board_cards", ["task_id"], schema="boards")

    op.create_table(
        "sprint_burndown_snapshots",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("sprint_id", pg.UUID(as_uuid=True), sa.ForeignKey("boards.sprints.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("remaining_points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("remaining_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("sprint_id", "snapshot_date", name="uq_sprint_burndown_sprint_date"),
        schema="boards",
    )
    op.create_index("ix_sprint_burndown_sprint_id", "sprint_burndown_snapshots", ["sprint_id"], schema="boards")

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
            "category IN ('board_change','column_change','card_change','sprint_change')",
            name="ck_boards_audit_logs_category",
        ),
        schema="boards",
    )
    op.create_index("ix_boards_audit_logs_org_id_occurred_at", "audit_logs", ["org_id", "occurred_at"], schema="boards")
    op.create_index("ix_boards_audit_logs_category", "audit_logs", ["category"], schema="boards")

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="boards",
    )
    op.create_index("ix_boards_outbox_messages_published_at", "outbox_messages", ["published_at"], schema="boards")


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="boards")
    op.drop_table("audit_logs", schema="boards")
    op.drop_table("sprint_burndown_snapshots", schema="boards")
    op.drop_table("board_cards", schema="boards")
    op.drop_table("sprints", schema="boards")
    op.drop_table("swimlanes", schema="boards")
    op.drop_table("board_columns", schema="boards")
    op.drop_table("boards_table", schema="boards")
    op.execute("DROP SCHEMA IF EXISTS boards CASCADE")
