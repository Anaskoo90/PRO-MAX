"""SQLAlchemy-backed implementations of the Ticket System repository Protocols."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ticket_system.domain.audit import TicketAuditEventCategory, TicketAuditLogRecord
from app.ticket_system.domain.entities import Ticket, TicketCategory
from app.ticket_system.infrastructure import mappers
from app.ticket_system.infrastructure.orm_models import (
    TicketAuditLogOrmModel,
    TicketCategoryOrmModel,
    TicketNumberSequenceOrmModel,
    TicketOrmModel,
)
from app.platform_core.api.sorting import SortField
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId

# Only fields with a real, indexed column behind them — no speculative
# sort/filter surface ahead of columns that don't exist yet (e.g. priority,
# tags — deferred to whichever later phase actually adds them).
_SORTABLE_COLUMNS = {
    "created_at": TicketOrmModel.created_at,
    "ticket_number": TicketOrmModel.ticket_number,
    "status": TicketOrmModel.status,
}


class SqlAlchemyTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, ticket_id: EntityId) -> Ticket | None:
        row = await self._session.get(TicketOrmModel, ticket_id)
        return mappers.ticket_to_domain(row) if row else None

    async def get_by_number(self, org_id: OrgId, ticket_number: int) -> Ticket | None:
        stmt = select(TicketOrmModel).where(
            TicketOrmModel.org_id == org_id, TicketOrmModel.ticket_number == ticket_number
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.ticket_to_domain(row) if row else None

    async def get_by_discord_channel_id(self, discord_channel_id: str) -> Ticket | None:
        """A channel can be reused after its ticket closes (the partial-
        unique index only forbids two *active* tickets sharing a channel,
        not a closed one being followed by a new one) — so more than one
        row can share discord_channel_id over time. The most recently
        created one is always the current ticket for that channel."""
        stmt = (
            select(TicketOrmModel)
            .where(TicketOrmModel.discord_channel_id == discord_channel_id)
            .order_by(TicketOrmModel.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.ticket_to_domain(row) if row else None

    async def list_for_org(self, org_id: OrgId, *, offset: int = 0, limit: int = 50) -> list[Ticket]:
        stmt = (
            select(TicketOrmModel)
            .where(TicketOrmModel.org_id == org_id)
            .order_by(TicketOrmModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.ticket_to_domain(r) for r in rows]

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
        filters = [TicketOrmModel.org_id == org_id]
        if status is not None:
            filters.append(TicketOrmModel.status == status)
        if claimed_by_discord_user_id is not None:
            filters.append(TicketOrmModel.claimed_by_discord_user_id == claimed_by_discord_user_id)

        count_stmt = select(func.count()).select_from(TicketOrmModel).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(TicketOrmModel).where(*filters)
        for sort_field in sort or []:
            column = _SORTABLE_COLUMNS[sort_field.field]
            stmt = stmt.order_by(column.desc() if sort_field.descending else column.asc())
        if not sort:
            stmt = stmt.order_by(TicketOrmModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.ticket_to_domain(r) for r in rows], total

    async def next_ticket_number(self, org_id: OrgId) -> int:
        """Atomic upsert-and-increment: a fresh org starts at 1; each
        subsequent call bumps and returns the next number. INSERT ... ON
        CONFLICT keeps this a single round-trip and safe under concurrent
        calls for the same org (the row-level lock taken by the UPDATE arm
        serializes concurrent callers)."""
        stmt = (
            pg_insert(TicketNumberSequenceOrmModel)
            .values(org_id=org_id, next_number=1)
            .on_conflict_do_update(
                index_elements=[TicketNumberSequenceOrmModel.org_id],
                set_={"next_number": TicketNumberSequenceOrmModel.next_number + 1},
            )
            .returning(TicketNumberSequenceOrmModel.next_number)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def add(self, ticket: Ticket) -> None:
        self._session.add(mappers.ticket_to_orm(ticket))

    async def update(self, ticket: Ticket) -> None:
        row = await self._session.get(TicketOrmModel, ticket.id)
        if row is None:
            raise ValueError(f"Ticket {ticket.id} not found for update")
        if row.version != ticket.version:
            raise ConcurrencyConflictError("Ticket", ticket.id)
        mappers.ticket_to_orm(ticket, row)
        row.version = ticket.version + 1
        ticket.version += 1


class SqlAlchemyTicketCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, category_id: EntityId) -> TicketCategory | None:
        row = await self._session.get(TicketCategoryOrmModel, category_id)
        return mappers.ticket_category_to_domain(row) if row else None

    async def list_for_guild(self, discord_guild_id: str, *, active_only: bool = True) -> list[TicketCategory]:
        stmt = select(TicketCategoryOrmModel).where(TicketCategoryOrmModel.discord_guild_id == discord_guild_id)
        if active_only:
            stmt = stmt.where(TicketCategoryOrmModel.is_active.is_(True))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.ticket_category_to_domain(r) for r in rows]

    async def add(self, category: TicketCategory) -> None:
        self._session.add(mappers.ticket_category_to_orm(category))

    async def update(self, category: TicketCategory) -> None:
        row = await self._session.get(TicketCategoryOrmModel, category.id)
        if row is None:
            raise ValueError(f"TicketCategory {category.id} not found for update")
        if row.version != category.version:
            raise ConcurrencyConflictError("TicketCategory", category.id)
        mappers.ticket_category_to_orm(category, row)
        row.version = category.version + 1
        category.version += 1


class SqlAlchemyTicketAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: TicketAuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: TicketAuditEventCategory | None = None, limit: int = 50
    ) -> list[TicketAuditLogRecord]:
        stmt = select(TicketAuditLogOrmModel).where(TicketAuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(TicketAuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(TicketAuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
