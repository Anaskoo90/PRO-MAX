"""SQLAlchemy-backed Team + TeamMembership repositories."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.team import Team, TeamMembership
from app.identity.infrastructure import mappers
from app.identity.infrastructure.orm_models import TeamMembershipOrmModel, TeamOrmModel
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class SqlAlchemyTeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, team_id: EntityId) -> Team | None:
        row = await self._session.get(TeamOrmModel, team_id)
        return mappers.team_to_domain(row) if row and not row.is_deleted else None

    async def list_for_org(self, org_id: OrgId) -> list[Team]:
        stmt = select(TeamOrmModel).where(TeamOrmModel.org_id == org_id, TeamOrmModel.is_deleted.is_(False))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.team_to_domain(r) for r in rows]

    async def add(self, team: Team) -> None:
        self._session.add(mappers.team_to_orm(team))

    async def update(self, team: Team) -> None:
        row = await self._session.get(TeamOrmModel, team.id)
        if row is None:
            raise ValueError(f"Team {team.id} not found for update")
        if row.version != team.version:
            raise ConcurrencyConflictError("Team", team.id)
        mappers.team_to_orm(team, row)
        row.version = team.version + 1
        team.version += 1


class SqlAlchemyTeamMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, team_id: EntityId, user_id: UserId) -> TeamMembership | None:
        stmt = select(TeamMembershipOrmModel).where(
            TeamMembershipOrmModel.team_id == team_id, TeamMembershipOrmModel.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.team_membership_to_domain(row) if row else None

    async def list_for_team(self, team_id: EntityId) -> list[TeamMembership]:
        stmt = select(TeamMembershipOrmModel).where(TeamMembershipOrmModel.team_id == team_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.team_membership_to_domain(r) for r in rows]

    async def list_for_user(self, user_id: UserId) -> list[TeamMembership]:
        stmt = select(TeamMembershipOrmModel).where(TeamMembershipOrmModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.team_membership_to_domain(r) for r in rows]

    async def add(self, membership: TeamMembership) -> None:
        self._session.add(mappers.team_membership_to_orm(membership))

    async def update(self, membership: TeamMembership) -> None:
        row = await self._session.get(TeamMembershipOrmModel, membership.id)
        if row is None:
            raise ValueError(f"TeamMembership {membership.id} not found for update")
        row.team_role = membership.team_role.value

    async def delete(self, membership_id: EntityId) -> None:
        row = await self._session.get(TeamMembershipOrmModel, membership_id)
        if row is not None:
            await self._session.delete(row)
