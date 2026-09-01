"""SQLAlchemy ORM models for the `discord_integration` schema —
infrastructure-layer only, per ADR-005..009 (domain layer never imports
this module).

org_id / requested_by_user_id / linked_by_user_id / revoked_by_user_id are
cross-schema references to identity.organizations / identity.users — not
hard FKs, per the platform's standing rule for cross-context refs (see
boards/infrastructure/orm_models.py's identical note)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_GUILD_LINK_STATUS_CHECK = "status IN ('active','revoked')"
_AUDIT_CATEGORY_CHECK = "category IN ('guild_link_change')"


class DiscordIntegrationBase(DeclarativeBase):
    # Same reasoning as every other context's Base: bare Mapped[datetime]
    # binds timezone-naive by default, but the actual Postgres columns are
    # TIMESTAMPTZ and utcnow() is tz-aware.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class GuildSetupTokenOrmModel(DiscordIntegrationBase):
    __tablename__ = "guild_setup_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_guild_setup_tokens_token_hash"),
        Index("ix_guild_setup_tokens_org_id", "org_id"),
        {"schema": "discord_integration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    consumed_by_discord_guild_id: Mapped[str | None] = mapped_column(String, nullable=True)


class GuildLinkOrmModel(DiscordIntegrationBase):
    __tablename__ = "guild_links"
    __table_args__ = (
        CheckConstraint(_GUILD_LINK_STATUS_CHECK, name="ck_guild_links_status"),
        Index("ix_guild_links_org_id", "org_id"),
        # At most one ACTIVE link per Discord guild at a time — a REVOKED
        # row doesn't block a fresh link elsewhere. Same partial-unique-index
        # technique as identity.uq_users_org_email / uq_organization_invitations_org_email_pending.
        Index(
            "uq_guild_links_discord_guild_id_active",
            "discord_guild_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        {"schema": "discord_integration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    discord_guild_id: Mapped[str] = mapped_column(String, nullable=False)
    discord_guild_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    linked_by_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class DiscordAuditLogOrmModel(DiscordIntegrationBase):
    """Append-only — no deleted_at, no update/delete in the repository."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_discord_integration_audit_logs_org_id_occurred_at", "org_id", "occurred_at"),
        Index("ix_discord_integration_audit_logs_category", "category"),
        CheckConstraint(_AUDIT_CATEGORY_CHECK, name="ck_discord_integration_audit_logs_category"),
        {"schema": "discord_integration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
