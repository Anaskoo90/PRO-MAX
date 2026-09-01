"""organization profile fields (description, logo_url)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("description", sa.String(), nullable=True), schema="identity")
    op.add_column("organizations", sa.Column("logo_url", sa.String(), nullable=True), schema="identity")


def downgrade() -> None:
    op.drop_column("organizations", "logo_url", schema="identity")
    op.drop_column("organizations", "description", schema="identity")
