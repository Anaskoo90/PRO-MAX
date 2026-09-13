"""link tickets to their ticket category

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("category_id", pg.UUID(as_uuid=True), nullable=True),
        schema="ticket_system",
    )
    op.create_foreign_key(
        "fk_tickets_category_id_ticket_categories",
        "tickets",
        "ticket_categories",
        ["category_id"],
        ["id"],
        source_schema="ticket_system",
        referent_schema="ticket_system",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tickets_category_id",
        "tickets",
        ["category_id"],
        schema="ticket_system",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tickets_category_id", table_name="tickets", schema="ticket_system"
    )
    op.drop_constraint(
        "fk_tickets_category_id_ticket_categories",
        "tickets",
        schema="ticket_system",
        type_="foreignkey",
    )
    op.drop_column("tickets", "category_id", schema="ticket_system")
