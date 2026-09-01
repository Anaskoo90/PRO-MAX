"""ticket_system Phase 1B: claim/unclaim/transfer + ticket_categories

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29

Additive: widens the tickets.status CHECK constraint to add 'claimed',
adds claimed_by_* columns, replaces the "open only" partial-unique index
on discord_channel_id with an "open or claimed" one (a claimed ticket's
channel is just as active as an open one), and creates the new
ticket_categories table. No existing row's data is touched.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TICKET_STATUS_CHECK = "status IN ('open','closed')"
_NEW_TICKET_STATUS_CHECK = "status IN ('open','claimed','closed')"
_ACTIVE_TICKET_STATUSES = "status IN ('open','claimed')"


def upgrade() -> None:
    op.drop_constraint("ck_tickets_status", "tickets", schema="ticket_system", type_="check")
    op.create_check_constraint(
        "ck_tickets_status", "tickets", _NEW_TICKET_STATUS_CHECK, schema="ticket_system"
    )

    op.add_column("tickets", sa.Column("claimed_by_discord_user_id", sa.String(), nullable=True), schema="ticket_system")
    op.add_column(
        "tickets", sa.Column("claimed_by_user_id", pg.UUID(as_uuid=True), nullable=True), schema="ticket_system"
    )

    op.drop_index("uq_tickets_discord_channel_id_open", table_name="tickets", schema="ticket_system")
    op.create_index(
        "uq_tickets_discord_channel_id_active",
        "tickets",
        ["discord_channel_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_TICKET_STATUSES),
        schema="ticket_system",
    )

    op.create_table(
        "ticket_categories",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("discord_guild_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("discord_category_channel_id", sa.String(), nullable=False),
        sa.Column("staff_discord_role_ids", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="ticket_system",
    )
    op.create_index(
        "ix_ticket_categories_discord_guild_id", "ticket_categories", ["discord_guild_id"], schema="ticket_system"
    )


def downgrade() -> None:
    op.drop_table("ticket_categories", schema="ticket_system")

    op.drop_index("uq_tickets_discord_channel_id_active", table_name="tickets", schema="ticket_system")
    op.create_index(
        "uq_tickets_discord_channel_id_open",
        "tickets",
        ["discord_channel_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        schema="ticket_system",
    )

    op.drop_column("tickets", "claimed_by_user_id", schema="ticket_system")
    op.drop_column("tickets", "claimed_by_discord_user_id", schema="ticket_system")

    op.drop_constraint("ck_tickets_status", "tickets", schema="ticket_system", type_="check")
    op.create_check_constraint(
        "ck_tickets_status", "tickets", _OLD_TICKET_STATUS_CHECK, schema="ticket_system"
    )
