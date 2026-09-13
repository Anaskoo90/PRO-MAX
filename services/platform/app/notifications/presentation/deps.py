from __future__ import annotations

from app.identity.presentation.deps import get_current_user_claims  # noqa: F401
from app.notifications.application.notification_service import NotificationService


def get_notification_service() -> NotificationService:
    raise NotImplementedError("NotificationService dependency not wired")
