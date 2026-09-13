from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.domain.entities import Notification, NotificationDeliveryAttempt
from app.notifications.infrastructure import mappers
from app.notifications.infrastructure.orm_models import (
    NotificationOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import utcnow


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, notification_id: EntityId) -> Notification | None:
        row = await self._session.get(NotificationOrmModel, notification_id)
        return mappers.notification_to_domain(row) if row else None

    async def list_visible_for_user(
        self,
        *,
        org_id: OrgId,
        user_id: UserId,
        unread_only: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Notification], int]:
        filters = [
            NotificationOrmModel.org_id == org_id,
            NotificationOrmModel.recipient_user_id == user_id,
            NotificationOrmModel.is_visible.is_(True),
        ]
        if unread_only:
            filters.append(NotificationOrmModel.read_at.is_(None))
        total = (
            await self._session.execute(
                select(func.count()).select_from(NotificationOrmModel).where(*filters)
            )
        ).scalar_one()
        rows = (
            await self._session.execute(
                select(NotificationOrmModel)
                .where(*filters)
                .order_by(NotificationOrmModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        return [mappers.notification_to_domain(row) for row in rows], total

    async def count_unread(self, *, org_id: OrgId, user_id: UserId) -> int:
        return (
            await self._session.execute(
                select(func.count())
                .select_from(NotificationOrmModel)
                .where(
                    NotificationOrmModel.org_id == org_id,
                    NotificationOrmModel.recipient_user_id == user_id,
                    NotificationOrmModel.is_visible.is_(True),
                    NotificationOrmModel.read_at.is_(None),
                )
            )
        ).scalar_one()

    async def add(self, notification: Notification) -> None:
        self._session.add(mappers.notification_to_orm(notification))

    async def update(self, notification: Notification) -> None:
        row = await self._session.get(NotificationOrmModel, notification.id)
        if row is None:
            raise ValueError(f"Notification {notification.id} not found for update")
        mappers.notification_to_orm(notification, row)

    async def mark_all_read(self, *, org_id: OrgId, user_id: UserId) -> None:
        await self._session.execute(
            update(NotificationOrmModel)
            .where(
                NotificationOrmModel.org_id == org_id,
                NotificationOrmModel.recipient_user_id == user_id,
                NotificationOrmModel.is_visible.is_(True),
                NotificationOrmModel.read_at.is_(None),
            )
            .values(read_at=utcnow())
        )


class SqlAlchemyNotificationDeliveryAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attempt: NotificationDeliveryAttempt) -> None:
        self._session.add(mappers.delivery_attempt_to_orm(attempt))
