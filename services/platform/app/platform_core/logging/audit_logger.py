"""
Audit Logging: distinct from application logging — audit entries are
business records (who did what, to what, when), written through the Audit
Center's append-only table (per the PostgreSQL Physical Schema), not the
general log pipeline. This wrapper standardizes the shape; the actual
persistence call is injected so platform_core doesn't depend on the Audit
Center's bounded-context repository.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.platform_core.shared_kernel.utils import utcnow


class AuditRecordSink(Protocol):
    async def write(self, record: "AuditRecord") -> None: ...


class AuditRecord:
    __slots__ = ("org_id", "actor_id", "action", "resource_type", "resource_id", "metadata", "occurred_at")

    def __init__(
        self,
        *,
        org_id: UUID,
        actor_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.org_id = org_id
        self.actor_id = actor_id
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.metadata = metadata or {}
        self.occurred_at = utcnow()


class AuditLogger:
    def __init__(self, sink: AuditRecordSink) -> None:
        self._sink = sink

    async def record(
        self,
        *,
        org_id: UUID,
        actor_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._sink.write(
            AuditRecord(
                org_id=org_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata,
            )
        )
