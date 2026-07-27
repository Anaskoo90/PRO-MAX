"""Teams submodule: create, update, delete, membership, roles, hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.identity.domain.exceptions import TeamHierarchyCycleError, TeamMembershipNotFoundError, TeamNotFoundError
from app.identity.domain.team import Team, TeamMembership, TeamRole
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


@dataclass(frozen=True, slots=True)
class TeamDTO:
    id: UUID
    org_id: UUID
    name: str
    description: str
    parent_team_id: UUID | None


@dataclass(frozen=True, slots=True)
class TeamMembershipDTO:
    id: UUID
    team_id: UUID
    user_id: UUID
    team_role: str


def _to_dto(team: Team) -> TeamDTO:
    return TeamDTO(id=team.id, org_id=team.org_id, name=team.name, description=team.description, parent_team_id=team.parent_team_id)


def _membership_to_dto(m: TeamMembership) -> TeamMembershipDTO:
    return TeamMembershipDTO(id=m.id, team_id=m.team_id, user_id=m.user_id, team_role=m.team_role.value)


class TeamService:
    def __init__(self, *, uow_factory, dispatcher: EventDispatcher) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher

    async def create_team(
        self, *, org_id: OrgId, name: str, description: str = "", parent_team_id: EntityId | None = None
    ) -> TeamDTO:
        async with self._uow_factory() as uow:
            team = Team.create(org_id=org_id, name=name, description=description, parent_team_id=parent_team_id)
            await uow.teams.add(team)
            events = team.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(team)

    async def update_team(self, *, team_id: EntityId, name: str | None, description: str | None) -> TeamDTO:
        async with self._uow_factory() as uow:
            team = await uow.teams.get_by_id(team_id)
            if team is None:
                raise TeamNotFoundError(team_id)
            team.update(name=name, description=description)
            await uow.teams.update(team)
            events = team.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(team)

    async def set_parent(self, *, team_id: EntityId, parent_team_id: EntityId | None) -> TeamDTO:
        async with self._uow_factory() as uow:
            team = await uow.teams.get_by_id(team_id)
            if team is None:
                raise TeamNotFoundError(team_id)

            if parent_team_id is not None:
                if parent_team_id == team_id:
                    raise TeamHierarchyCycleError()
                teams_by_id: dict[EntityId, Team] = {}
                cursor: EntityId | None = parent_team_id
                while cursor is not None:
                    if cursor == team_id:
                        raise TeamHierarchyCycleError()
                    ancestor = teams_by_id.get(cursor) or await uow.teams.get_by_id(cursor)
                    if ancestor is None:
                        break
                    teams_by_id[cursor] = ancestor
                    cursor = ancestor.parent_team_id

            team.set_parent(parent_team_id)
            await uow.teams.update(team)
            events = team.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(team)

    async def delete_team(self, *, team_id: EntityId) -> None:
        async with self._uow_factory() as uow:
            team = await uow.teams.get_by_id(team_id)
            if team is None:
                raise TeamNotFoundError(team_id)
            team.delete()
            await uow.teams.update(team)
            events = team.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def add_member(self, *, team_id: EntityId, user_id: UserId, team_role: TeamRole = TeamRole.MEMBER) -> TeamMembershipDTO:
        async with self._uow_factory() as uow:
            if await uow.teams.get_by_id(team_id) is None:
                raise TeamNotFoundError(team_id)
            existing = await uow.team_memberships.get(team_id, user_id)
            if existing is not None:
                return _membership_to_dto(existing)
            membership = TeamMembership.create(team_id=team_id, user_id=user_id, team_role=team_role)
            await uow.team_memberships.add(membership)
            await uow.commit()
            return _membership_to_dto(membership)

    async def update_member_role(self, *, team_id: EntityId, user_id: UserId, team_role: TeamRole) -> TeamMembershipDTO:
        async with self._uow_factory() as uow:
            membership = await uow.team_memberships.get(team_id, user_id)
            if membership is None:
                raise TeamMembershipNotFoundError(team_id, user_id)
            membership.team_role = team_role
            await uow.team_memberships.update(membership)
            await uow.commit()
            return _membership_to_dto(membership)

    async def remove_member(self, *, team_id: EntityId, user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            membership = await uow.team_memberships.get(team_id, user_id)
            if membership is None:
                raise TeamMembershipNotFoundError(team_id, user_id)
            await uow.team_memberships.delete(membership.id)
            await uow.commit()

    async def list_members(self, *, team_id: EntityId) -> list[TeamMembershipDTO]:
        async with self._uow_factory() as uow:
            memberships = await uow.team_memberships.list_for_team(team_id)
            return [_membership_to_dto(m) for m in memberships]

    async def list_teams_for_org(self, *, org_id: OrgId) -> list[TeamDTO]:
        async with self._uow_factory() as uow:
            teams = await uow.teams.list_for_org(org_id)
            return [_to_dto(t) for t in teams]
