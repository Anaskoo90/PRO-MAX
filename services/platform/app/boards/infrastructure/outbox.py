"""Outbox table + writer for the `boards` schema (Outbox Pattern, ADR-014) —
identical mechanism to every other context's outbox, kept as this
context's own table per schema-per-bounded-context (ADR-001)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.platform_core.events.contracts import IntegrationEvent
from app.boards.infrastructure.orm_models import BoardsBase


class OutboxMessageOrmModel(BoardsBase):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        Index("ix_boards_outbox_messages_published_at", "published_at"),
        {"schema": "boards"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str]
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SqlAlchemyOutboxWriter:
    def __init__(self, session: AsyncSession, *, event_type: str) -> None:
        self._session = session
        self._event_type = event_type

    async def append(self, event: IntegrationEvent) -> None:
        self._session.add(
            OutboxMessageOrmModel(
                id=event.event_id, event_type=self._event_type, org_id=event.org_id,
                payload=event.model_dump(mode="json"),
            )
        )
