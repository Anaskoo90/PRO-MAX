from __future__ import annotations

from uuid import UUID

from app.notifications.domain.entities import (
    DeliveryAttemptStatus,
    Notification,
    NotificationDeliveryAttempt,
)
from app.platform_core.notifications.dispatcher import NotificationRequest
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class SqlAlchemyNotificationDeliveryRecorder:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def begin(self, request: NotificationRequest) -> UUID:
        notification = Notification.create(
            org_id=OrgId(request.org_id),
            recipient_user_id=(
                UserId(request.recipient_user_id)
                if request.recipient_user_id is not None
                else None
            ),
            channel=request.channel.value,
            recipient=request.recipient,
            subject=request.subject,
            safe_body=request.in_app_body,
            metadata=request.metadata,
        )
        async with self._uow_factory() as uow:
            await uow.notifications.add(notification)
            await uow.commit()
        return notification.id

    async def mark_delivered(self, notification_id: UUID) -> None:
        await self._finish(
            notification_id=notification_id,
            status=DeliveryAttemptStatus.DELIVERED,
        )

    async def mark_failed(
        self, notification_id: UUID, *, failure_type: str
    ) -> None:
        await self._finish(
            notification_id=notification_id,
            status=DeliveryAttemptStatus.FAILED,
            failure_type=failure_type,
        )

    async def _finish(
        self,
        *,
        notification_id: UUID,
        status: DeliveryAttemptStatus,
        failure_type: str | None = None,
    ) -> None:
        async with self._uow_factory() as uow:
            notification = await uow.notifications.get_by_id(
                EntityId(notification_id)
            )
            if notification is None:
                raise ValueError(
                    f"Notification {notification_id} not found for delivery update"
                )
            if status is DeliveryAttemptStatus.DELIVERED:
                notification.mark_delivered()
            else:
                notification.mark_failed(failure_type=failure_type or "UnknownError")
            await uow.notifications.update(notification)
            await uow.delivery_attempts.add(
                NotificationDeliveryAttempt.create(
                    notification_id=notification.id,
                    status=status,
                    failure_type=failure_type,
                )
            )
            await uow.commit()
