from __future__ import annotations

from typing import Protocol

from app.notifications.domain.entities import Notification, NotificationDeliveryAttempt
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class NotificationRepository(Protocol):
    async def get_by_id(self, notification_id: EntityId) -> Notification | None: ...
    async def list_visible_for_user(
        self,
        *,
        org_id: OrgId,
        user_id: UserId,
        unread_only: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Notification], int]: ...
    async def count_unread(self, *, org_id: OrgId, user_id: UserId) -> int: ...
    async def add(self, notification: Notification) -> None: ...
    async def update(self, notification: Notification) -> None: ...
    async def mark_all_read(self, *, org_id: OrgId, user_id: UserId) -> None: ...


class NotificationDeliveryAttemptRepository(Protocol):
    async def add(self, attempt: NotificationDeliveryAttempt) -> None: ...
