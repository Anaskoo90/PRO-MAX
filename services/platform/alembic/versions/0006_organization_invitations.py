"""organization invitations

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.organizations.id"), nullable=False
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.roles.id"), nullable=False),
        sa.Column(
            "invited_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False
        ),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_organization_invitations_token_hash"),
        schema="identity",
    )
    op.create_index(
        "ix_organization_invitations_org_id", "organization_invitations", ["org_id"], schema="identity"
    )
    op.create_index(
        "ix_organization_invitations_email", "organization_invitations", ["email"], schema="identity"
    )
    # At most one PENDING invitation per (org, email) at a time — matches
    # users.uq_users_org_email's partial-index approach (0001) for the same
    # reason: accepted/revoked rows must remain in history, not block a
    # fresh invite to the same address later.
    op.create_index(
        "uq_organization_invitations_org_email_pending",
        "organization_invitations",
        ["org_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_table("organization_invitations", schema="identity")
