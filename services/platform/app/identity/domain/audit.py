"""
Audit Logs submodule.

Append-only by construction — AuditLogRecord has no update/delete methods
and no `deleted_at`, matching the platform-wide convention for historical
records. Covers the six categories the phase objective named:
Authentication Events, Authorization Events, User Changes, Role Changes,
Permission Changes, Organization Changes — expressed as a flat `category` +
`action` pair rather than six separate tables, since they share an
identical shape and the category is just a filter dimension.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class AuditEventCategory(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    USER_CHANGE = "user_change"
    ROLE_CHANGE = "role_change"
    PERMISSION_CHANGE = "permission_change"
    ORGANIZATION_CHANGE = "organization_change"


class AuditLogRecord:
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        category: AuditEventCategory,
        action: str,
        actor_user_id: UserId | None,
        resource_type: str,
        resource_id: str,
        ip_address: str | None,
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
        self.ip_address = ip_address
        self.metadata = metadata or {}
        self.occurred_at = occurred_at or utcnow()

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        category: AuditEventCategory,
        action: str,
        actor_user_id: UserId | None,
        resource_type: str,
        resource_id: str,
        ip_address: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AuditLogRecord":
        return cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            category=category,
            action=action,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            metadata=metadata,
        )
