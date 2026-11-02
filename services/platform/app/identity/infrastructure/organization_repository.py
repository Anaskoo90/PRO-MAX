"""SQLAlchemy-backed Organization repository."""

from __future__ import annotations

from sqlalchemy import select, update
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

    async def get_by_id_for_update(self, org_id: EntityId) -> Organization | None:
        """Load the organization and take a row lock (`SELECT ... FOR UPDATE`)
        held until the unit of work commits or rolls back.

        Lock order: operations that touch ownership-sensitive state (ownership
        transfer, user suspension/deactivation, revoking the owner role) take
        THIS lock first, before reading or writing any user, role or
        assignment row. A single, fixed first lock means two of them can
        queue behind each other but never deadlock on it.

        `populate_existing` refreshes an instance already in the session's
        identity map, so the caller always sees the state committed by
        whichever transaction held the lock before it.
        """
        stmt = (
            select(OrganizationOrmModel)
            .where(OrganizationOrmModel.id == org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
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
        """Optimistic-concurrency update enforced by the database.

        The version is claimed with a conditional UPDATE
        (`... WHERE id = :id AND version = :loaded_version RETURNING id`). A
        transaction that loaded a stale version matches no row and gets
        ConcurrencyConflictError; the claim also takes the row lock, so a
        concurrent writer waits for us and then fails the predicate instead
        of silently overwriting (a lost update).
        The previous check was a read-then-compare in Python
        (`row.version != organization.version`): two overlapping transactions
        both passed the compare before either had written, and the second
        UPDATE (which carried no version predicate) then overwrote the first —
        a lost update. It only caught conflicts that had already committed
        before the re-read, and even that depended on the ORM identity map
        having dropped its cached row.
        """
        claimed = await self._session.execute(
            update(OrganizationOrmModel)
            .where(
                OrganizationOrmModel.id == organization.id,
                OrganizationOrmModel.version == organization.version,
            )
            .values(version=organization.version + 1)
            .returning(OrganizationOrmModel.id)
            .execution_options(synchronize_session=False)
        )
        if claimed.first() is None:  # no row matched id AND version -> someone else got there first
            raise ConcurrencyConflictError("Organization", organization.id)
        row = await self._session.get(OrganizationOrmModel, organization.id)
        if row is None:
            raise ValueError(f"Organization {organization.id} not found for update")
        mappers.organization_to_orm(organization, row)
        row.version = organization.version + 1
        organization.version += 1
