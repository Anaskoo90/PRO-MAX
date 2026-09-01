"""Repository interfaces (Protocols) — satisfied by infrastructure/repositories.py.
Application layer depends only on these, mirroring every prior context's
dependency rule exactly."""

from __future__ import annotations

from typing import Protocol

from app.ticket_system.domain.audit import TicketAuditEventCategory, TicketAuditLogRecord
from app.ticket_system.domain.entities import Ticket, TicketCategory
from app.platform_core.api.sorting import SortField
from app.platform_core.shared_kernel.types import EntityId, OrgId


class TicketRepository(Protocol):
    async def get_by_id(self, ticket_id: EntityId) -> Ticket | None: ...
    async def get_by_number(self, org_id: OrgId, ticket_number: int) -> Ticket | None: ...
    async def get_by_discord_channel_id(self, discord_channel_id: str) -> Ticket | None: ...
    async def list_for_org(self, org_id: OrgId, *, offset: int = 0, limit: int = 50) -> list[Ticket]: ...
    async def search(
        self,
        org_id: OrgId,
        *,
        status: str | None = None,
        claimed_by_discord_user_id: str | None = None,
        sort: list[SortField] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Ticket], int]:
        """Dashboard-facing listing: filters (currently status/claimed_by —
        the only fields a ticket actually has that are worth filtering on
        today), sort, and the total match count needed for pagination UI.
        Returns (page_of_tickets, total_matching_count)."""
        ...
    async def next_ticket_number(self, org_id: OrgId) -> int: ...
    async def add(self, ticket: Ticket) -> None: ...
    async def update(self, ticket: Ticket) -> None: ...


class TicketCategoryRepository(Protocol):
    async def get_by_id(self, category_id: EntityId) -> TicketCategory | None: ...
    async def list_for_guild(self, discord_guild_id: str, *, active_only: bool = True) -> list[TicketCategory]: ...
    async def add(self, category: TicketCategory) -> None: ...
    async def update(self, category: TicketCategory) -> None: ...


class TicketAuditLogRepository(Protocol):
    async def add(self, record: TicketAuditLogRecord) -> None: ...
    async def list_for_org(
        self, org_id: OrgId, *, category: TicketAuditEventCategory | None = None, limit: int = 50
    ) -> list[TicketAuditLogRecord]: ...
