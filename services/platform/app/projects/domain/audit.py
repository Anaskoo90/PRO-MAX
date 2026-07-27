"""
Projects & Workspaces' own append-only audit trail — reuses the exact
AuditLogRecord *pattern* Identity established (append-only, no update/
delete, category + action + actor + resource shape), kept in this
context's own schema rather than writing into identity.audit_logs, per
ADR-001's schema-per-bounded-context (an audit table is still a table).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class ProjectsAuditEventCategory(StrEnum):
    WORKSPACE_CHANGE = "workspace_change"
    PROJECT_CHANGE = "project_change"
    MEMBERSHIP_CHANGE = "membership_change"
    TEMPLATE_CHANGE = "template_change"


class ProjectsAuditLogRecord:
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        category: ProjectsAuditEventCategory,
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
        category: ProjectsAuditEventCategory,
        action: str,
        actor_user_id: UserId | None,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> "ProjectsAuditLogRecord":
        return cls(
            id=EntityId(new_uuid7()), org_id=org_id, category=category, action=action, actor_user_id=actor_user_id,
            resource_type=resource_type, resource_id=resource_id, metadata=metadata,
        )
