import pytest

from app.identity.application.team_management import TeamService
from app.identity.domain.exceptions import TeamNotFoundError
from app.identity.domain.team import Team, TeamMembership, TeamRole
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


class _Teams:
    def __init__(self, team: Team) -> None:
        self.team = team

    async def get_by_id(self, team_id: EntityId) -> Team | None:
        return self.team if team_id == self.team.id else None

    async def update(self, team: Team) -> None:
        self.team = team


class _Memberships:
    def __init__(self, membership: TeamMembership) -> None:
        self.membership = membership
        self.deleted = False

    async def get(self, team_id: EntityId, user_id: UserId) -> TeamMembership | None:
        if not self.deleted and (team_id, user_id) == (self.membership.team_id, self.membership.user_id):
            return self.membership
        return None

    async def add(self, membership: TeamMembership) -> None:
        self.membership = membership

    async def update(self, membership: TeamMembership) -> None:
        self.membership = membership

    async def delete(self, membership_id: EntityId) -> None:
        assert membership_id == self.membership.id
        self.deleted = True


class _UnitOfWork:
    def __init__(self, team: Team, membership: TeamMembership) -> None:
        self.teams = _Teams(team)
        self.team_memberships = _Memberships(membership)

    async def __aenter__(self) -> "_UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_org_a_cannot_modify_org_b_team_or_its_memberships() -> None:
    org_a = OrgId(new_uuid7())
    org_b = OrgId(new_uuid7())
    team_b = Team.create(org_id=org_b, name="Organization B Team")
    member_b = TeamMembership.create(team_id=team_b.id, user_id=UserId(new_uuid7()))
    uow = _UnitOfWork(team_b, member_b)
    service = TeamService(uow_factory=lambda: uow, dispatcher=EventDispatcher())

    with pytest.raises(TeamNotFoundError):
        await service.update_team(org_id=org_a, team_id=team_b.id, name="Compromised", description=None)
    with pytest.raises(TeamNotFoundError):
        await service.delete_team(org_id=org_a, team_id=team_b.id)
    with pytest.raises(TeamNotFoundError):
        await service.add_member(org_id=org_a, team_id=team_b.id, user_id=UserId(new_uuid7()))
    with pytest.raises(TeamNotFoundError):
        await service.update_member_role(
            org_id=org_a, team_id=team_b.id, user_id=member_b.user_id, team_role=TeamRole.LEAD
        )
    with pytest.raises(TeamNotFoundError):
        await service.remove_member(org_id=org_a, team_id=team_b.id, user_id=member_b.user_id)

    assert team_b.name == "Organization B Team"
    assert team_b.is_deleted is False
    assert member_b.team_role is TeamRole.MEMBER
    assert uow.team_memberships.deleted is False


@pytest.mark.asyncio
async def test_org_a_cannot_list_org_b_team_memberships() -> None:
    org_a = OrgId(new_uuid7())
    team_b = Team.create(org_id=OrgId(new_uuid7()), name="Organization B Team")
    member_b = TeamMembership.create(team_id=team_b.id, user_id=UserId(new_uuid7()))
    service = TeamService(uow_factory=lambda: _UnitOfWork(team_b, member_b), dispatcher=EventDispatcher())

    with pytest.raises(TeamNotFoundError):
        await service.list_members_for_org(org_id=org_a, team_id=team_b.id)
