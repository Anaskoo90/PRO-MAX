"""
Application-layer ports: the only way this bounded context is allowed to
reach Identity (ADR-005..009's cross-context dependency rule — forbidden
except through an Event Bus or an explicit Anti-Corruption Layer). Mirrors
every prior context's application/ports.py exactly.

- OrgPermissionCheckerPort is satisfied structurally, no adapter class
  needed, by Identity's real PermissionEvaluator instance (same as Boards/
  Tasks/Workflow Engine).
- OrganizationLookupPort *does* need a real adapter (infrastructure/
  identity_adapter.py) since its method name doesn't structurally match
  OrganizationManagementService's.
- DiscordIntegrationUnitOfWorkPort mirrors every prior context's UnitOfWork
  port exactly.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.discord_integration.domain.repositories import (
    DiscordAuditLogRepository,
    GuildLinkRepository,
    GuildSetupTokenRepository,
)
from app.platform_core.events.publisher import OutboxWriter


class DiscordIntegrationUnitOfWorkPort(Protocol):
    guild_setup_tokens: GuildSetupTokenRepository
    guild_links: GuildLinkRepository
    audit_logs: DiscordAuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "DiscordIntegrationUnitOfWorkPort": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class OrgPermissionCheckerPort(Protocol):
    async def has_permission(self, *, user_id: UUID, org_id: UUID, resource: str, action: str) -> bool: ...


class OrganizationLookupPort(Protocol):
    async def get_org_name(self, *, org_id: UUID) -> str | None: ...
