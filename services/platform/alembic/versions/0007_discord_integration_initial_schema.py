"""discord_integration initial schema

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUILD_LINK_STATUS_CHECK = "status IN ('active','revoked')"
_AUDIT_CATEGORY_CHECK = "category IN ('guild_link_change')"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS discord_integration")

    op.create_table(
        "guild_setup_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("requested_by_user_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consumed_by_discord_guild_id", sa.String(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_guild_setup_tokens_token_hash"),
        schema="discord_integration",
    )
    op.create_index(
        "ix_guild_setup_tokens_org_id", "guild_setup_tokens", ["org_id"], schema="discord_integration"
    )

    op.create_table(
        "guild_links",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("discord_guild_id", sa.String(), nullable=False),
        sa.Column("discord_guild_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("linked_by_user_id", pg.UUID(as_uuid=True), nullable=False),  # cross-schema, no hard FK
        sa.Column("linked_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", pg.UUID(as_uuid=True), nullable=True),  # cross-schema, no hard FK
        sa.Column("settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(_GUILD_LINK_STATUS_CHECK, name="ck_guild_links_status"),
        schema="discord_integration",
    )
    op.create_index("ix_guild_links_org_id", "guild_links", ["org_id"], schema="discord_integration")
    # At most one ACTIVE link per Discord guild at a time — a REVOKED row
    # doesn't block a fresh link elsewhere. Same partial-unique-index
    # technique as identity.uq_users_org_email (0001) /
    # uq_organization_invitations_org_email_pending (0006).
    op.create_index(
        "uq_guild_links_discord_guild_id_active",
        "guild_links",
        ["discord_guild_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        schema="discord_integration",
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
        sa.CheckConstraint(_AUDIT_CATEGORY_CHECK, name="ck_discord_integration_audit_logs_category"),
        schema="discord_integration",
    )
    op.create_index(
        "ix_discord_integration_audit_logs_org_id_occurred_at",
        "audit_logs",
        ["org_id", "occurred_at"],
        schema="discord_integration",
    )
    op.create_index(
        "ix_discord_integration_audit_logs_category", "audit_logs", ["category"], schema="discord_integration"
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="discord_integration",
    )
    op.create_index(
        "ix_discord_integration_outbox_messages_published_at",
        "outbox_messages",
        ["published_at"],
        schema="discord_integration",
    )


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="discord_integration")
    op.drop_table("audit_logs", schema="discord_integration")
    op.drop_table("guild_links", schema="discord_integration")
    op.drop_table("guild_setup_tokens", schema="discord_integration")
