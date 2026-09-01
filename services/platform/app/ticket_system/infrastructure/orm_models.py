"""SQLAlchemy ORM models for the `ticket_system` schema — infrastructure-
layer only, per ADR-005..009 (domain layer never imports this module).

org_id / discord_guild_id / opener_*/closed_*_user_id are cross-schema
references to identity.organizations / identity.users — not hard FKs, per
the platform's standing rule for cross-context refs (see boards/
infrastructure/orm_models.py's identical note)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Widened in Phase 1B (migration 0009) to add 'claimed' — same incremental
# discipline as every other addition in this context (see entities.py's
# module docstring).
_TICKET_STATUS_CHECK = "status IN ('open','claimed','closed')"
_ACTIVE_TICKET_STATUSES = "status IN ('open','claimed')"


class TicketSystemBase(DeclarativeBase):
    # Same reasoning as every other context's Base: bare Mapped[datetime]
    # binds timezone-naive by default, but the actual Postgres columns are
    # TIMESTAMPTZ and utcnow() is tz-aware.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class TicketOrmModel(TicketSystemBase):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(_TICKET_STATUS_CHECK, name="ck_tickets_status"),
        UniqueConstraint("org_id", "ticket_number", name="uq_tickets_org_id_ticket_number"),
        Index("ix_tickets_org_id", "org_id"),
        Index("ix_tickets_org_id_status", "org_id", "status"),
        # At most one active (open or claimed) ticket per Discord channel —
        # a closed ticket's channel could in principle be reused/archived
        # later.
        Index(
            "uq_tickets_discord_channel_id_active",
            "discord_channel_id",
            unique=True,
            postgresql_where=text(_ACTIVE_TICKET_STATUSES),
        ),
        # Plain (non-partial) index so get_by_discord_channel_id — the
        # hottest bot-facing lookup, hit on every control-view button press
        # — doesn't fall back to a sequential scan once a ticket is closed
        # (the partial index above only covers open/claimed rows).
        Index("ix_tickets_discord_channel_id", "discord_channel_id"),
        {"schema": "ticket_system"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    discord_guild_id: Mapped[str] = mapped_column(String, nullable=False)
    ticket_number: Mapped[int] = mapped_column(Integer, nullable=False)
    discord_channel_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    opener_discord_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    opener_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    claimed_by_discord_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_by_discord_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class TicketNumberSequenceOrmModel(TicketSystemBase):
    """One row per org — next_ticket_number() upserts and increments this
    atomically so concurrent ticket creation never allocates duplicate
    numbers within an org."""

    __tablename__ = "ticket_number_sequences"
    __table_args__ = ({"schema": "ticket_system"},)

    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TicketCategoryOrmModel(TicketSystemBase):
    __tablename__ = "ticket_categories"
    __table_args__ = (
        Index("ix_ticket_categories_discord_guild_id", "discord_guild_id"),
        {"schema": "ticket_system"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    discord_guild_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    discord_category_channel_id: Mapped[str] = mapped_column(String, nullable=False)
    staff_discord_role_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TicketAuditLogOrmModel(TicketSystemBase):
    """Append-only — no deleted_at, no update/delete in the repository."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_ticket_system_audit_logs_org_id_occurred_at", "org_id", "occurred_at"),
        Index("ix_ticket_system_audit_logs_category", "category"),
        CheckConstraint("category IN ('ticket_change')", name="ck_ticket_system_audit_logs_category"),
        {"schema": "ticket_system"},
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
