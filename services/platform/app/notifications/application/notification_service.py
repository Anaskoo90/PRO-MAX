from __future__ import annotations

from dataclasses import dataclass

from app.notifications.application.dtos import NotificationDTO, notification_to_dto
from app.notifications.domain.exceptions import NotificationNotFoundError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


@dataclass(frozen=True, slots=True)
class NotificationPage:
    items: list[NotificationDTO]
    total: int


class NotificationService:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def list_for_user(
        self,
        *,
        org_id: OrgId,
        user_id: UserId,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> NotificationPage:
        async with self._uow_factory() as uow:
            records, total = await uow.notifications.list_visible_for_user(
                org_id=org_id,
                user_id=user_id,
                unread_only=unread_only,
                offset=offset,
                limit=limit,
            )
        return NotificationPage(
            items=[notification_to_dto(record) for record in records],
            total=total,
        )

    async def count_unread(self, *, org_id: OrgId, user_id: UserId) -> int:
        async with self._uow_factory() as uow:
            return await uow.notifications.count_unread(
                org_id=org_id, user_id=user_id
            )

    async def mark_read(
        self, *, org_id: OrgId, user_id: UserId, notification_id: EntityId
    ) -> None:
        async with self._uow_factory() as uow:
            notification = await uow.notifications.get_by_id(notification_id)
            if (
                notification is None
                or notification.org_id != org_id
                or notification.recipient_user_id != user_id
                or not notification.is_visible
            ):
                raise NotificationNotFoundError(notification_id)
            notification.mark_read()
            await uow.notifications.update(notification)
            await uow.commit()

    async def mark_all_read(self, *, org_id: OrgId, user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            await uow.notifications.mark_all_read(org_id=org_id, user_id=user_id)
            await uow.commit()
