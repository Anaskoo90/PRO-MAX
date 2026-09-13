from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.notifications.domain.entities import Notification


@dataclass(frozen=True, slots=True)
class NotificationDTO:
    id: UUID
    org_id: UUID
    channel: str
    subject: str | None
    body: str
    metadata: dict[str, Any]
    status: str
    created_at: datetime
    delivered_at: datetime | None
    read_at: datetime | None


def notification_to_dto(notification: Notification) -> NotificationDTO:
    return NotificationDTO(
        id=notification.id,
        org_id=notification.org_id,
        channel=notification.channel,
        subject=notification.subject,
        body=notification.body,
        metadata=notification.metadata,
        status=notification.status.value,
        created_at=notification.created_at,
        delivered_at=notification.delivered_at,
        read_at=notification.read_at,
    )
