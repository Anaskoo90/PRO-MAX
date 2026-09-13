from __future__ import annotations

from app.notifications.domain.entities import (
    DeliveryAttemptStatus,
    Notification,
    NotificationDeliveryAttempt,
    NotificationStatus,
)
from app.notifications.infrastructure.orm_models import (
    NotificationDeliveryAttemptOrmModel,
    NotificationOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def notification_to_domain(row: NotificationOrmModel) -> Notification:
    return Notification(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        recipient_user_id=(
            UserId(row.recipient_user_id) if row.recipient_user_id else None
        ),
        channel=row.channel,
        recipient=row.recipient,
        subject=row.subject,
        body=row.body,
        metadata=row.metadata_,
        is_visible=row.is_visible,
        status=NotificationStatus(row.status),
        failure_type=row.failure_type,
        created_at=row.created_at,
        delivered_at=row.delivered_at,
        read_at=row.read_at,
    )


def notification_to_orm(
    notification: Notification, row: NotificationOrmModel | None = None
) -> NotificationOrmModel:
    values = {
        "id": notification.id,
        "org_id": notification.org_id,
        "recipient_user_id": notification.recipient_user_id,
        "channel": notification.channel,
        "recipient": notification.recipient,
        "subject": notification.subject,
        "body": notification.body,
        "metadata_": notification.metadata,
        "is_visible": notification.is_visible,
        "status": notification.status.value,
        "failure_type": notification.failure_type,
        "created_at": notification.created_at,
        "delivered_at": notification.delivered_at,
        "read_at": notification.read_at,
    }
    if row is None:
        return NotificationOrmModel(**values)
    for key, value in values.items():
        setattr(row, key, value)
    return row


def delivery_attempt_to_orm(
    attempt: NotificationDeliveryAttempt,
) -> NotificationDeliveryAttemptOrmModel:
    return NotificationDeliveryAttemptOrmModel(
        id=attempt.id,
        notification_id=attempt.notification_id,
        status=attempt.status.value,
        failure_type=attempt.failure_type,
        attempted_at=attempt.attempted_at,
    )


def delivery_attempt_to_domain(
    row: NotificationDeliveryAttemptOrmModel,
) -> NotificationDeliveryAttempt:
    return NotificationDeliveryAttempt(
        id=EntityId(row.id),
        notification_id=EntityId(row.notification_id),
        status=DeliveryAttemptStatus(row.status),
        failure_type=row.failure_type,
        attempted_at=row.attempted_at,
    )
