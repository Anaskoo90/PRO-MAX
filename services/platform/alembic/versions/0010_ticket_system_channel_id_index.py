"""ticket_system Phase 1C: plain index on tickets.discord_channel_id

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-29

Purely additive: adds a normal (non-partial) index alongside the existing
uq_tickets_discord_channel_id_active partial unique index, so
get_by_discord_channel_id — called on every bot control-view button press
— has an index to use once a ticket is no longer open/claimed (the
partial index only covers active rows). No column, constraint, or data
change.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_tickets_discord_channel_id", "tickets", ["discord_channel_id"], schema="ticket_system"
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_discord_channel_id", table_name="tickets", schema="ticket_system")
