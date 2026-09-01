"""ticket_system initial schema (Phase 1A: create/open/close only)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-29

Deliberately narrow: only what Phase 1A's Ticket create/open/close needs.
Claim/unclaim/transfer (Phase 1B) and everything after (categories,
templates, SLA, messages, history, attachments, transcripts) get their own
small additive migrations when those phases land, rather than
speculatively creating tables/columns no code uses yet — same discipline
every prior migration in this repo already follows.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TICKET_STATUS_CHECK = "status IN ('open','closed')"
_AUDIT_CATEGORY_CHECK = "category IN ('ticket_change')"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ticket_system")

    op.create_table(
        "ticket_number_sequences",
        sa.Column("org_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        schema="ticket_system",
    )

    op.create_table(
        "tickets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("discord_guild_id", sa.String(), nullable=False),
        sa.Column("ticket_number", sa.Integer(), nullable=False),
        sa.Column("discord_channel_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("opener_discord_user_id", sa.String(), nullable=True),
        sa.Column("opener_user_id", pg.UUID(as_uuid=True), nullable=True),  # cross-schema, no hard FK
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_by_discord_user_id", sa.String(), nullable=True),
        sa.Column("closed_by_user_id", pg.UUID(as_uuid=True), nullable=True),  # cross-schema, no hard FK
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(_TICKET_STATUS_CHECK, name="ck_tickets_status"),
        sa.UniqueConstraint("org_id", "ticket_number", name="uq_tickets_org_id_ticket_number"),
        schema="ticket_system",
    )
    op.create_index("ix_tickets_org_id", "tickets", ["org_id"], schema="ticket_system")
    op.create_index("ix_tickets_org_id_status", "tickets", ["org_id", "status"], schema="ticket_system")
    # At most one OPEN ticket per Discord channel at a time — matches
    # every other context's partial-unique-index technique (e.g.
    # identity.uq_users_org_email, discord_integration.
    # uq_guild_links_discord_guild_id_active).
    op.create_index(
        "uq_tickets_discord_channel_id_open",
        "tickets",
        ["discord_channel_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        schema="ticket_system",
    )

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
        sa.CheckConstraint(_AUDIT_CATEGORY_CHECK, name="ck_ticket_system_audit_logs_category"),
        schema="ticket_system",
    )
    op.create_index(
        "ix_ticket_system_audit_logs_org_id_occurred_at", "audit_logs", ["org_id", "occurred_at"],
        schema="ticket_system",
    )
    op.create_index(
        "ix_ticket_system_audit_logs_category", "audit_logs", ["category"], schema="ticket_system"
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ticket_system",
    )
    op.create_index(
        "ix_ticket_system_outbox_messages_published_at", "outbox_messages", ["published_at"],
        schema="ticket_system",
    )


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="ticket_system")
    op.drop_table("audit_logs", schema="ticket_system")
    op.drop_table("tickets", schema="ticket_system")
    op.drop_table("ticket_number_sequences", schema="ticket_system")
