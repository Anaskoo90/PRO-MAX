"""SQLAlchemy-backed AuditLogRecord repository — replaces the placeholder
logging-only sink from the earlier Authentication/User Management bootstrap
with real, queryable, append-only persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import AuditLogOrmModel
from app.platform_core.shared_kernel.types import OrgId


class SqlAlchemyAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: AuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: AuditEventCategory | None = None, limit: int = 50
    ) -> list[AuditLogRecord]:
        stmt = select(AuditLogOrmModel).where(AuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(AuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(AuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
