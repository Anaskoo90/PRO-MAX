"""Discord Integration's own append-only audit trail — same pattern
established by every prior context's own audit log, kept in this
context's own schema per ADR-001 (schema-per-bounded-context)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class DiscordAuditEventCategory(StrEnum):
    GUILD_LINK_CHANGE = "guild_link_change"


class DiscordAuditLogRecord:
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        category: DiscordAuditEventCategory,
        action: str,
        actor_user_id: UserId | None,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.org_id = org_id
        self.category = category
        self.action = action
        self.actor_user_id = actor_user_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.metadata = metadata or {}
        self.occurred_at = occurred_at or utcnow()

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        category: DiscordAuditEventCategory,
        action: str,
        actor_user_id: UserId | None,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> "DiscordAuditLogRecord":
        return cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            category=category,
            action=action,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
