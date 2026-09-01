"""SQLAlchemy-backed Organization Invitation repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.invitation import InvitationStatus, OrganizationInvitation
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import OrganizationInvitationOrmModel
from app.platform_core.shared_kernel.types import EntityId, OrgId


class SqlAlchemyOrganizationInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, invitation_id: EntityId) -> OrganizationInvitation | None:
        row = await self._session.get(OrganizationInvitationOrmModel, invitation_id)
        return mappers.organization_invitation_to_domain(row) if row else None

    async def get_by_token_hash(self, token_hash: str) -> OrganizationInvitation | None:
        stmt = select(OrganizationInvitationOrmModel).where(
            OrganizationInvitationOrmModel.token_hash == token_hash
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.organization_invitation_to_domain(row) if row else None

    async def get_pending_for_email(self, org_id: OrgId, email: str) -> OrganizationInvitation | None:
        stmt = select(OrganizationInvitationOrmModel).where(
            OrganizationInvitationOrmModel.org_id == org_id,
            OrganizationInvitationOrmModel.email == email,
            OrganizationInvitationOrmModel.status == InvitationStatus.PENDING.value,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.organization_invitation_to_domain(row) if row else None

    async def list_pending_for_org(
        self, org_id: OrgId, *, offset: int = 0, limit: int = 50
    ) -> list[OrganizationInvitation]:
        stmt = (
            select(OrganizationInvitationOrmModel)
            .where(
                OrganizationInvitationOrmModel.org_id == org_id,
                OrganizationInvitationOrmModel.status == InvitationStatus.PENDING.value,
            )
            .order_by(OrganizationInvitationOrmModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.organization_invitation_to_domain(r) for r in rows]

    async def add(self, invitation: OrganizationInvitation) -> None:
        self._session.add(mappers.organization_invitation_to_orm(invitation))

    async def update(self, invitation: OrganizationInvitation) -> None:
        row = await self._session.get(OrganizationInvitationOrmModel, invitation.id)
        if row is None:
            raise ValueError(f"OrganizationInvitation {invitation.id} not found for update")
        mappers.organization_invitation_to_orm(invitation, row)
