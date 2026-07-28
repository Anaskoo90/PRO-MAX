"""Unit of Work for the `boards` schema — one AsyncSession per request/
command, one commit, identical shape to every other context's UnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.boards.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.boards.infrastructure.repositories import (
    SqlAlchemyBoardCardRepository,
    SqlAlchemyBoardColumnRepository,
    SqlAlchemyBoardRepository,
    SqlAlchemyBoardsAuditLogRepository,
    SqlAlchemySprintBurndownSnapshotRepository,
    SqlAlchemySprintRepository,
    SqlAlchemySwimlaneRepository,
)


class BoardsUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.boards: SqlAlchemyBoardRepository | None = None
        self.board_columns: SqlAlchemyBoardColumnRepository | None = None
        self.swimlanes: SqlAlchemySwimlaneRepository | None = None
        self.board_cards: SqlAlchemyBoardCardRepository | None = None
        self.sprints: SqlAlchemySprintRepository | None = None
        self.sprint_burndown_snapshots: SqlAlchemySprintBurndownSnapshotRepository | None = None
        self.audit_logs: SqlAlchemyBoardsAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "BoardsUnitOfWork":
        self.session = self._session_factory()
        self.boards = SqlAlchemyBoardRepository(self.session)
        self.board_columns = SqlAlchemyBoardColumnRepository(self.session)
        self.swimlanes = SqlAlchemySwimlaneRepository(self.session)
        self.board_cards = SqlAlchemyBoardCardRepository(self.session)
        self.sprints = SqlAlchemySprintRepository(self.session)
        self.sprint_burndown_snapshots = SqlAlchemySprintBurndownSnapshotRepository(self.session)
        self.audit_logs = SqlAlchemyBoardsAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="boards.integration_event")
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
