from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
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


class UnreadNotificationCountResponse(BaseModel):
    count: int
