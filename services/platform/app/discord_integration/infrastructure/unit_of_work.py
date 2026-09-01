"""Unit of Work for the `discord_integration` schema — one AsyncSession per
request/command, one commit, identical shape to every other context's
UnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discord_integration.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.discord_integration.infrastructure.repositories import (
    SqlAlchemyDiscordAuditLogRepository,
    SqlAlchemyGuildLinkRepository,
    SqlAlchemyGuildSetupTokenRepository,
)


class DiscordIntegrationUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.guild_setup_tokens: SqlAlchemyGuildSetupTokenRepository | None = None
        self.guild_links: SqlAlchemyGuildLinkRepository | None = None
        self.audit_logs: SqlAlchemyDiscordAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "DiscordIntegrationUnitOfWork":
        self.session = self._session_factory()
        self.guild_setup_tokens = SqlAlchemyGuildSetupTokenRepository(self.session)
        self.guild_links = SqlAlchemyGuildLinkRepository(self.session)
        self.audit_logs = SqlAlchemyDiscordAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="discord_integration.integration_event")
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
