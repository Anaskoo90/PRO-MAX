"""In-memory fakes satisfying the Discord Integration repository Protocols
and application ports — mirrors tests/boards/unit/fakes.py exactly."""

from __future__ import annotations

from app.discord_integration.domain.entities import GuildLink, GuildSetupToken
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import utcnow


class FakeGuildSetupTokenRepository:
    def __init__(self) -> None:
        self.tokens: dict[EntityId, GuildSetupToken] = {}

    async def get_by_token_hash(self, token_hash: str) -> GuildSetupToken | None:
        return next((t for t in self.tokens.values() if t.token_hash == token_hash), None)

    async def add(self, token: GuildSetupToken) -> None:
        self.tokens[token.id] = token

    async def update(self, token: GuildSetupToken) -> None:
        self.tokens[token.id] = token

    async def invalidate_outstanding_for_org(self, org_id: OrgId) -> None:
        for token in self.tokens.values():
            if token.org_id == org_id and token.consumed_at is None:
                token.consumed_at = utcnow()


class FakeGuildLinkRepository:
    def __init__(self) -> None:
        self.links: dict[EntityId, GuildLink] = {}

    async def get_by_id(self, guild_link_id: EntityId) -> GuildLink | None:
        return self.links.get(guild_link_id)

    async def get_by_discord_guild_id(self, discord_guild_id: str) -> GuildLink | None:
        return next((l for l in self.links.values() if l.discord_guild_id == discord_guild_id), None)

    async def get_active_by_discord_guild_id(self, discord_guild_id: str) -> GuildLink | None:
        return next(
            (l for l in self.links.values() if l.discord_guild_id == discord_guild_id and l.is_active()), None
        )

    async def list_for_org(self, org_id: OrgId) -> list[GuildLink]:
        return [l for l in self.links.values() if l.org_id == org_id]

    async def add(self, link: GuildLink) -> None:
        self.links[link.id] = link

    async def update(self, link: GuildLink) -> None:
        self.links[link.id] = link


class FakeDiscordAuditLogRepository:
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


class FakeDiscordIntegrationUnitOfWork:
    def __init__(self) -> None:
        self.guild_setup_tokens = FakeGuildSetupTokenRepository()
        self.guild_links = FakeGuildLinkRepository()
        self.audit_logs = FakeDiscordAuditLogRepository()
        self.outbox = FakeOutboxWriter()

    async def __aenter__(self) -> "FakeDiscordIntegrationUnitOfWork":
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


class FakeOrganizationLookup:
    def __init__(self, *, names: dict | None = None) -> None:
        self._names = names or {}

    async def get_org_name(self, *, org_id) -> str | None:
        return self._names.get(org_id)
