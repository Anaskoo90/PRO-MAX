"""ticket attachments

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_attachments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by_discord_user_id", sa.String(), nullable=True),
        sa.Column("discord_attachment_id", sa.String(), nullable=True),
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
            "storage_key", name="uq_ticket_attachments_storage_key"
        ),
        sa.UniqueConstraint(
            "discord_attachment_id",
            name="uq_ticket_attachments_discord_attachment_id",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_ticket_attachments_size"),
        sa.CheckConstraint(
            "char_length(sha256) = 64", name="ck_ticket_attachments_sha256"
        ),
        schema="ticket_system",
    )
    op.create_index(
        "ix_ticket_attachments_org_ticket_created_at",
        "ticket_attachments",
        ["org_id", "ticket_id", "created_at"],
        schema="ticket_system",
    )


def downgrade() -> None:
    op.drop_table("ticket_attachments", schema="ticket_system")
