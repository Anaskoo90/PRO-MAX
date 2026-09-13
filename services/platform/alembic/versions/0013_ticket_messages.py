"""ticket messages

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.String(length=10_000), nullable=False),
        sa.Column("author_discord_user_id", sa.String(), nullable=True),
        sa.Column("author_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("discord_message_id", sa.String(), nullable=True),
        sa.Column(
            "is_internal", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket_system.tickets.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "discord_message_id",
            name="uq_ticket_messages_discord_message_id",
        ),
        schema="ticket_system",
    )
    op.create_index(
        "ix_ticket_messages_org_ticket_created_at",
        "ticket_messages",
        ["org_id", "ticket_id", "created_at"],
        schema="ticket_system",
    )


def downgrade() -> None:
    op.drop_table("ticket_messages", schema="ticket_system")
