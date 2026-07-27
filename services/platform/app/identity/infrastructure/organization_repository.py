"""SQLAlchemy-backed Organization repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.organization import Organization
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import OrganizationOrmModel
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId


class SqlAlchemyOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, org_id: EntityId) -> Organization | None:
        row = await self._session.get(OrganizationOrmModel, org_id)
        return mappers.organization_to_domain(row) if row and row.deleted_at is None else None

    async def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(OrganizationOrmModel).where(
            OrganizationOrmModel.slug == slug, OrganizationOrmModel.deleted_at.is_(None)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.organization_to_domain(row) if row else None

    async def add(self, organization: Organization) -> None:
        self._session.add(mappers.organization_to_orm(organization))

    async def update(self, organization: Organization) -> None:
        row = await self._session.get(OrganizationOrmModel, organization.id)
        if row is None:
            raise ValueError(f"Organization {organization.id} not found for update")
        if row.version != organization.version:
            raise ConcurrencyConflictError("Organization", organization.id)
        mappers.organization_to_orm(organization, row)
        row.version = organization.version + 1
        organization.version += 1
