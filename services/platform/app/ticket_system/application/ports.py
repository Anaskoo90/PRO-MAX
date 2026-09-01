"""
Application-layer ports: the only way this bounded context is allowed to
reach Identity or Discord Integration (ADR-005..009's cross-context
dependency rule). Mirrors every prior context's application/ports.py
exactly.

- OrgPermissionCheckerPort is satisfied structurally, no adapter class
  needed, by Identity's real PermissionEvaluator instance (same as every
  prior context's reuse of it).
- GuildResolverPort *does* need a real adapter (infrastructure/
  discord_integration_adapter.py), since its method doesn't structurally
  match DiscordSetupService's.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform_core.events.publisher import OutboxWriter
from app.ticket_system.domain.repositories import (
    TicketAuditLogRepository,
    TicketCategoryRepository,
    TicketRepository,
)


class TicketUnitOfWorkPort(Protocol):
    tickets: TicketRepository
    ticket_categories: TicketCategoryRepository
    audit_logs: TicketAuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "TicketUnitOfWorkPort": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class OrgPermissionCheckerPort(Protocol):
    async def has_permission(self, *, user_id: UUID, org_id: UUID, resource: str, action: str) -> bool: ...


class GuildResolverPort(Protocol):
    async def resolve_org_id(self, *, discord_guild_id: str) -> UUID | None: ...
