from __future__ import annotations

from app.platform_core.errors.domain_exceptions import EntityNotFoundError


class NotificationNotFoundError(EntityNotFoundError):
    def __init__(self, notification_id: object) -> None:
        super().__init__("Notification", notification_id)
