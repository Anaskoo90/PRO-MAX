"""In-memory fakes satisfying the Ticket System repository Protocols and
application ports — mirrors tests/boards/unit/fakes.py exactly."""

from __future__ import annotations

from app.ticket_system.domain.entities import Ticket, TicketCategory
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId


class FakeTicketRepository:
    def __init__(self) -> None:
        self.tickets: dict[EntityId, Ticket] = {}
        self._next_numbers: dict[OrgId, int] = {}

    async def get_by_id(self, ticket_id: EntityId) -> Ticket | None:
        return self.tickets.get(ticket_id)

    async def get_by_number(self, org_id: OrgId, ticket_number: int) -> Ticket | None:
        return next(
            (t for t in self.tickets.values() if t.org_id == org_id and t.ticket_number == ticket_number), None
        )

    async def get_by_discord_channel_id(self, discord_channel_id: str) -> Ticket | None:
        return next((t for t in self.tickets.values() if t.discord_channel_id == discord_channel_id), None)

    async def list_for_org(self, org_id: OrgId, *, offset: int = 0, limit: int = 50) -> list[Ticket]:
        matches = [t for t in self.tickets.values() if t.org_id == org_id]
        return matches[offset : offset + limit]

    async def search(
        self,
        org_id: OrgId,
        *,
        status: str | None = None,
        claimed_by_discord_user_id: str | None = None,
        sort=None,
        offset: int = 0,
        limit: int = 50,
    ):
        matches = [t for t in self.tickets.values() if t.org_id == org_id]
        if status is not None:
            matches = [t for t in matches if t.status.value == status]
        if claimed_by_discord_user_id is not None:
            matches = [t for t in matches if t.claimed_by_discord_user_id == claimed_by_discord_user_id]

        for sort_field in reversed(sort or []):
            matches.sort(key=lambda t: getattr(t, sort_field.field), reverse=sort_field.descending)
        if not sort:
            matches.sort(key=lambda t: t.created_at, reverse=True)

        total = len(matches)
        return matches[offset : offset + limit], total

    async def next_ticket_number(self, org_id: OrgId) -> int:
        current = self._next_numbers.get(org_id, 0) + 1
        self._next_numbers[org_id] = current
        return current

    async def add(self, ticket: Ticket) -> None:
        self.tickets[ticket.id] = ticket

    async def update(self, ticket: Ticket) -> None:
        self.tickets[ticket.id] = ticket


class FakeTicketCategoryRepository:
    def __init__(self) -> None:
        self.categories: dict[EntityId, TicketCategory] = {}

    async def get_by_id(self, category_id: EntityId) -> TicketCategory | None:
        return self.categories.get(category_id)

    async def list_for_guild(self, discord_guild_id: str, *, active_only: bool = True) -> list[TicketCategory]:
        matches = [c for c in self.categories.values() if c.discord_guild_id == discord_guild_id]
        if active_only:
            matches = [c for c in matches if c.is_active]
        return matches

    async def add(self, category: TicketCategory) -> None:
        self.categories[category.id] = category

    async def update(self, category: TicketCategory) -> None:
        existing = self.categories.get(category.id)
        if existing is not None and existing.version != category.version:
            raise ConcurrencyConflictError("TicketCategory", category.id)
        self.categories[category.id] = category


class FakeTicketAuditLogRepository:
    def __init__(self) -> None:
        self.records: list = []

    async def add(self, record) -> None:
        self.records.append(record)

    async def list_for_org(self, org_id, *, category=None, limit: int = 50):
        results = [r for r in self.records if r.org_id == org_id]
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:limit]


class FakeOutboxWriter:
    async def append(self, event) -> None:
        pass


class FakeTicketUnitOfWork:
    def __init__(self) -> None:
        self.tickets = FakeTicketRepository()
        self.ticket_categories = FakeTicketCategoryRepository()
        self.audit_logs = FakeTicketAuditLogRepository()
        self.outbox = FakeOutboxWriter()

    async def __aenter__(self) -> "FakeTicketUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class AllowAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return True


class DenyAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return False


class AllowOnlyActionsPermissionChecker:
    """Grants exactly the given set of `ticket:<action>` actions and denies
    everything else — lets a test prove *which* permission a service
    method actually checks, rather than just allow-everything/deny-
    everything."""

    def __init__(self, *, allowed_actions: set[str]) -> None:
        self._allowed_actions = allowed_actions

    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return action in self._allowed_actions


class FakeGuildResolver:
    def __init__(self, *, org_ids_by_guild: dict | None = None) -> None:
        self._org_ids_by_guild = org_ids_by_guild or {}

    async def resolve_org_id(self, *, discord_guild_id: str):
        return self._org_ids_by_guild.get(discord_guild_id)
