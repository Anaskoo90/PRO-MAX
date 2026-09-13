from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.notifications.infrastructure.repositories import (
    SqlAlchemyNotificationDeliveryAttemptRepository,
    SqlAlchemyNotificationRepository,
)


class NotificationsUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.notifications: SqlAlchemyNotificationRepository | None = None
        self.delivery_attempts: (
            SqlAlchemyNotificationDeliveryAttemptRepository | None
        ) = None

    async def __aenter__(self) -> NotificationsUnitOfWork:
        self.session = self._session_factory()
        self.notifications = SqlAlchemyNotificationRepository(self.session)
        self.delivery_attempts = SqlAlchemyNotificationDeliveryAttemptRepository(
            self.session
        )
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
