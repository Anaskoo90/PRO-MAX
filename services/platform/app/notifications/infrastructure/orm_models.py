from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class NotificationsBase(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class NotificationOrmModel(NotificationsBase):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('email','push','sms','in_app')",
            name="ck_notifications_channel",
        ),
        CheckConstraint(
            "status IN ('pending','delivered','failed')",
            name="ck_notifications_status",
        ),
        Index(
            "ix_notifications_user_created_at",
            "recipient_user_id",
            "created_at",
        ),
        Index("ix_notifications_org_status", "org_id", "status"),
        {"schema": "notifications"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    recipient: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    failure_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)


class NotificationDeliveryAttemptOrmModel(NotificationsBase):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('delivered','failed')",
            name="ck_notification_delivery_attempts_status",
        ),
        Index(
            "ix_notification_delivery_attempts_notification_id_attempted_at",
            "notification_id",
            "attempted_at",
        ),
        {"schema": "notifications"},
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("notifications.notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    failure_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
