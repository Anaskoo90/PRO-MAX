from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class NotificationStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class DeliveryAttemptStatus(StrEnum):
    DELIVERED = "delivered"
    FAILED = "failed"


class Notification:
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        recipient_user_id: UserId | None,
        channel: str,
        recipient: str,
        subject: str | None,
        body: str,
        metadata: dict[str, Any] | None,
        is_visible: bool,
        status: NotificationStatus,
        failure_type: str | None = None,
        created_at: datetime | None = None,
        delivered_at: datetime | None = None,
        read_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.org_id = org_id
        self.recipient_user_id = recipient_user_id
        self.channel = channel
        self.recipient = recipient
        self.subject = subject
        self.body = body
        self.metadata = metadata or {}
        self.is_visible = is_visible
        self.status = status
        self.failure_type = failure_type
        self.created_at = created_at or utcnow()
        self.delivered_at = delivered_at
        self.read_at = read_at

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        recipient_user_id: UserId | None,
        channel: str,
        recipient: str,
        subject: str | None,
        safe_body: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        return cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            recipient_user_id=recipient_user_id,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=safe_body or "",
            metadata=metadata,
            is_visible=recipient_user_id is not None and safe_body is not None,
            status=NotificationStatus.PENDING,
        )

    def mark_delivered(self) -> None:
        self.status = NotificationStatus.DELIVERED
        self.failure_type = None
        self.delivered_at = utcnow()

    def mark_failed(self, *, failure_type: str) -> None:
        self.status = NotificationStatus.FAILED
        self.failure_type = failure_type[:200]

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = utcnow()


class NotificationDeliveryAttempt:
    def __init__(
        self,
        *,
        id: EntityId,
        notification_id: EntityId,
        status: DeliveryAttemptStatus,
        failure_type: str | None = None,
        attempted_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.notification_id = notification_id
        self.status = status
        self.failure_type = failure_type
        self.attempted_at = attempted_at or utcnow()

    @classmethod
    def create(
        cls,
        *,
        notification_id: EntityId,
        status: DeliveryAttemptStatus,
        failure_type: str | None = None,
    ) -> NotificationDeliveryAttempt:
        return cls(
            id=EntityId(new_uuid7()),
            notification_id=notification_id,
            status=status,
            failure_type=failure_type[:200] if failure_type else None,
        )
