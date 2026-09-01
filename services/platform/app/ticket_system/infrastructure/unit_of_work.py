"""Unit of Work for the `ticket_system` schema — one AsyncSession per
request/command, one commit, identical shape to every other context's
UnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ticket_system.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.ticket_system.infrastructure.repositories import (
    SqlAlchemyTicketAuditLogRepository,
    SqlAlchemyTicketCategoryRepository,
    SqlAlchemyTicketRepository,
)


class TicketUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.tickets: SqlAlchemyTicketRepository | None = None
        self.ticket_categories: SqlAlchemyTicketCategoryRepository | None = None
        self.audit_logs: SqlAlchemyTicketAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "TicketUnitOfWork":
        self.session = self._session_factory()
        self.tickets = SqlAlchemyTicketRepository(self.session)
        self.ticket_categories = SqlAlchemyTicketCategoryRepository(self.session)
        self.audit_logs = SqlAlchemyTicketAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="ticket_system.integration_event")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()
