from __future__ import annotations

import pytest
from app.notifications.application.notification_service import NotificationService
from app.notifications.domain.entities import Notification
from app.notifications.domain.exceptions import NotificationNotFoundError
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


class _Notifications:
    def __init__(self, records: list[Notification]) -> None:
        self.records = {record.id: record for record in records}

    async def get_by_id(self, notification_id):
        return self.records.get(notification_id)

    async def list_visible_for_user(
        self, *, org_id, user_id, unread_only, offset, limit
    ):
        records = [
            record
            for record in self.records.values()
            if record.org_id == org_id
            and record.recipient_user_id == user_id
            and record.is_visible
            and (not unread_only or record.read_at is None)
        ]
        return records[offset : offset + limit], len(records)

    async def count_unread(self, *, org_id, user_id):
        records, total = await self.list_visible_for_user(
            org_id=org_id,
            user_id=user_id,
            unread_only=True,
            offset=0,
            limit=10_000,
        )
        return total

    async def update(self, notification) -> None:
        self.records[notification.id] = notification

    async def mark_all_read(self, *, org_id, user_id) -> None:
        for record in self.records.values():
            if (
                record.org_id == org_id
                and record.recipient_user_id == user_id
                and record.is_visible
            ):
                record.mark_read()


class _UnitOfWork:
    def __init__(self, notifications: _Notifications) -> None:
        self.notifications = notifications

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None


def _notification(org_id: OrgId, user_id: UserId) -> Notification:
    return Notification.create(
        org_id=org_id,
        recipient_user_id=user_id,
        channel="in_app",
        recipient=str(user_id),
        subject="Task assigned",
        safe_body="You were assigned a task.",
    )


async def test_user_only_lists_their_own_tenants_visible_notifications() -> None:
    org_a = OrgId(new_uuid7())
    org_b = OrgId(new_uuid7())
    user_a = UserId(new_uuid7())
    records = _Notifications(
        [
            _notification(org_a, user_a),
            _notification(org_a, UserId(new_uuid7())),
            _notification(org_b, user_a),
        ]
    )
    service = NotificationService(uow_factory=lambda: _UnitOfWork(records))

    page = await service.list_for_user(org_id=org_a, user_id=user_a)

    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].org_id == org_a


async def test_user_cannot_mark_another_users_notification_read() -> None:
    org_id = OrgId(new_uuid7())
    owner_id = UserId(new_uuid7())
    record = _notification(org_id, owner_id)
    records = _Notifications([record])
    service = NotificationService(uow_factory=lambda: _UnitOfWork(records))

    with pytest.raises(NotificationNotFoundError):
        await service.mark_read(
            org_id=org_id,
            user_id=UserId(new_uuid7()),
            notification_id=record.id,
        )

    assert record.read_at is None


async def test_same_user_can_mark_one_or_all_notifications_read() -> None:
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())
    first = _notification(org_id, user_id)
    second = _notification(org_id, user_id)
    records = _Notifications([first, second])
    service = NotificationService(uow_factory=lambda: _UnitOfWork(records))

    await service.mark_read(
        org_id=org_id, user_id=user_id, notification_id=first.id
    )
    assert await service.count_unread(org_id=org_id, user_id=user_id) == 1

    await service.mark_all_read(org_id=org_id, user_id=user_id)

    assert await service.count_unread(org_id=org_id, user_id=user_id) == 0
