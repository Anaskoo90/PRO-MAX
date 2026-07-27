"""identity initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")

    op.create_table(
        "organizations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("owner_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        schema="identity",
    )
    op.create_index("ix_organizations_status", "organizations", ["status"], schema="identity")

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.organizations.id"), nullable=False
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending_verification"),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("preferences", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("avatar_storage_key", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index(
        "uq_users_org_email", "users", ["org_id", "email"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"), schema="identity",
    )
    op.create_index("ix_users_org_status", "users", ["org_id", "status"], schema="identity")

    op.create_table(
        "sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(), nullable=False),
        sa.Column("device_info", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ip_address", pg.INET(), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema="identity")
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], schema="identity")

    op.create_table(
        "mfa_factors",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("factor_type", sa.String(), nullable=False),
        sa.Column("secret_encrypted", sa.String(), nullable=True),
        sa.Column("recovery_code_hash", sa.String(), nullable=True),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="identity",
    )
    op.create_index("ix_mfa_factors_user_id", "mfa_factors", ["user_id"], schema="identity")

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index(
        "ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"], schema="identity"
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], schema="identity")

    op.create_table(
        "password_history",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="identity",
    )
    op.create_index(
        "ix_password_history_user_id_created_at", "password_history", ["user_id", "created_at"], schema="identity"
    )

    op.create_table(
        "teams",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.organizations.id"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("parent_team_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.teams.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="identity",
    )
    op.create_index("ix_teams_org_id", "teams", ["org_id"], schema="identity")

    op.create_table(
        "team_memberships",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.teams.id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("team_role", sa.String(), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
        schema="identity",
    )
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"], schema="identity")

    op.create_table(
        "roles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.organizations.id"), nullable=True
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("is_system_role", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parent_role_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.roles.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="identity",
    )
    op.create_index("ix_roles_org_id", "roles", ["org_id"], schema="identity")

    op.create_table(
        "permissions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),
        schema="identity",
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.roles.id"), nullable=False),
        sa.Column(
            "permission_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.permissions.id"), nullable=False
        ),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        schema="identity",
    )

    op.create_table(
        "user_roles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("role_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.roles.id"), nullable=False),
        sa.Column(
            "org_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.organizations.id"), nullable=False
        ),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        schema="identity",
    )
    op.create_index("ix_user_roles_org_id", "user_roles", ["org_id"], schema="identity")

    op.create_table(
        "trusted_devices",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("device_fingerprint_hash", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False, server_default=""),
        sa.Column("trusted_until", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "device_fingerprint_hash", name="uq_trusted_devices_user_fingerprint"),
        schema="identity",
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),  # no FK — audit writes must never block on it
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("ip_address", pg.INET(), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="identity",
    )
    op.create_index("ix_audit_logs_org_id_occurred_at", "audit_logs", ["org_id", "occurred_at"], schema="identity")
    op.create_index("ix_audit_logs_category", "audit_logs", ["category"], schema="identity")

    op.create_table(
        "outbox_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index("ix_outbox_messages_published_at", "outbox_messages", ["published_at"], schema="identity")


def downgrade() -> None:
    op.drop_table("outbox_messages", schema="identity")
    op.drop_table("audit_logs", schema="identity")
    op.drop_table("trusted_devices", schema="identity")
    op.drop_table("user_roles", schema="identity")
    op.drop_table("role_permissions", schema="identity")
    op.drop_table("permissions", schema="identity")
    op.drop_table("roles", schema="identity")
    op.drop_table("team_memberships", schema="identity")
    op.drop_table("teams", schema="identity")
    op.drop_table("password_history", schema="identity")
    op.drop_table("password_reset_tokens", schema="identity")
    op.drop_table("email_verification_tokens", schema="identity")
    op.drop_table("mfa_factors", schema="identity")
    op.drop_table("sessions", schema="identity")
    op.drop_table("users", schema="identity")
    op.drop_table("organizations", schema="identity")
    op.execute("DROP SCHEMA IF EXISTS identity CASCADE")
