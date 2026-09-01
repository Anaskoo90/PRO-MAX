"""SQLAlchemy-backed implementations of the Discord Integration repository Protocols."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.discord_integration.domain.audit import DiscordAuditEventCategory, DiscordAuditLogRecord
from app.discord_integration.domain.entities import GuildLink, GuildSetupToken
from app.discord_integration.infrastructure import mappers
from app.discord_integration.infrastructure.orm_models import (
    DiscordAuditLogOrmModel,
    GuildLinkOrmModel,
    GuildSetupTokenOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import utcnow


class SqlAlchemyGuildSetupTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token_hash(self, token_hash: str) -> GuildSetupToken | None:
        stmt = select(GuildSetupTokenOrmModel).where(GuildSetupTokenOrmModel.token_hash == token_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.guild_setup_token_to_domain(row) if row else None

    async def add(self, token: GuildSetupToken) -> None:
        self._session.add(mappers.guild_setup_token_to_orm(token))

    async def update(self, token: GuildSetupToken) -> None:
        row = await self._session.get(GuildSetupTokenOrmModel, token.id)
        if row is None:
            raise ValueError(f"GuildSetupToken {token.id} not found for update")
        mappers.guild_setup_token_to_orm(token, row)

    async def invalidate_outstanding_for_org(self, org_id: OrgId) -> None:
        stmt = (
            update(GuildSetupTokenOrmModel)
            .where(GuildSetupTokenOrmModel.org_id == org_id, GuildSetupTokenOrmModel.consumed_at.is_(None))
            .values(consumed_at=utcnow())
        )
        await self._session.execute(stmt)


class SqlAlchemyGuildLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, guild_link_id: EntityId) -> GuildLink | None:
        row = await self._session.get(GuildLinkOrmModel, guild_link_id)
        return mappers.guild_link_to_domain(row) if row else None

    async def get_by_discord_guild_id(self, discord_guild_id: str) -> GuildLink | None:
        stmt = select(GuildLinkOrmModel).where(GuildLinkOrmModel.discord_guild_id == discord_guild_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.guild_link_to_domain(row) if row else None

    async def get_active_by_discord_guild_id(self, discord_guild_id: str) -> GuildLink | None:
        stmt = select(GuildLinkOrmModel).where(
            GuildLinkOrmModel.discord_guild_id == discord_guild_id, GuildLinkOrmModel.status == "active"
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.guild_link_to_domain(row) if row else None

    async def list_for_org(self, org_id: OrgId) -> list[GuildLink]:
        stmt = select(GuildLinkOrmModel).where(GuildLinkOrmModel.org_id == org_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.guild_link_to_domain(r) for r in rows]

    async def add(self, link: GuildLink) -> None:
        self._session.add(mappers.guild_link_to_orm(link))

    async def update(self, link: GuildLink) -> None:
        row = await self._session.get(GuildLinkOrmModel, link.id)
        if row is None:
            raise ValueError(f"GuildLink {link.id} not found for update")
        if row.version != link.version:
            raise ConcurrencyConflictError("GuildLink", link.id)
        mappers.guild_link_to_orm(link, row)
        row.version = link.version + 1
        link.version += 1


class SqlAlchemyDiscordAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: DiscordAuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: DiscordAuditEventCategory | None = None, limit: int = 50
    ) -> list[DiscordAuditLogRecord]:
        stmt = select(DiscordAuditLogOrmModel).where(DiscordAuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(DiscordAuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(DiscordAuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
