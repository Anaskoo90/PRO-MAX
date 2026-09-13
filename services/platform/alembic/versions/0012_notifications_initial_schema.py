"""notifications initial schema

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications")
    op.create_table(
        "notifications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("failure_type", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "channel IN ('email','push','sms','in_app')",
            name="ck_notifications_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending','delivered','failed')",
            name="ck_notifications_status",
        ),
        schema="notifications",
    )
    op.create_index(
        "ix_notifications_user_created_at",
        "notifications",
        ["recipient_user_id", "created_at"],
        schema="notifications",
    )
    op.create_index(
        "ix_notifications_org_status",
        "notifications",
        ["org_id", "status"],
        schema="notifications",
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey(
                "notifications.notifications.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_type", sa.String(length=200), nullable=True),
        sa.Column(
            "attempted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('delivered','failed')",
            name="ck_notification_delivery_attempts_status",
        ),
        schema="notifications",
    )
    op.create_index(
        "ix_notification_delivery_attempts_notification_id_attempted_at",
        "delivery_attempts",
        ["notification_id", "attempted_at"],
        schema="notifications",
    )


def downgrade() -> None:
    op.drop_table("delivery_attempts", schema="notifications")
    op.drop_table("notifications", schema="notifications")
    op.execute("DROP SCHEMA IF EXISTS notifications")
