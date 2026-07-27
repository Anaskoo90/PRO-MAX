from app.identity.domain.events import TeamCreated, TeamDeleted
from app.identity.domain.team import Team, TeamMembership, TeamRole
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_create_records_team_created_event() -> None:
    org_id = OrgId(new_uuid7())
    team = Team.create(org_id=org_id, name="Platform")

    events = team.pull_domain_events()
    assert isinstance(events[0], TeamCreated)
    assert events[0].org_id == org_id
    assert team.parent_team_id is None


def test_update_changes_name_and_description() -> None:
    team = Team.create(org_id=OrgId(new_uuid7()), name="Platform")
    team.pull_domain_events()

    team.update(name="Core Platform", description="Owns platform_core")

    assert team.name == "Core Platform"
    assert team.description == "Owns platform_core"


def test_delete_marks_deleted_and_records_event() -> None:
    team = Team.create(org_id=OrgId(new_uuid7()), name="Platform")
    team.pull_domain_events()

    team.delete()

    assert team.is_deleted is True
    events = team.pull_domain_events()
    assert isinstance(events[0], TeamDeleted)


def test_set_parent_updates_parent_team_id() -> None:
    parent_id = EntityId(new_uuid7())
    team = Team.create(org_id=OrgId(new_uuid7()), name="Platform")

    team.set_parent(parent_id)

    assert team.parent_team_id == parent_id


def test_team_membership_defaults_to_member_role() -> None:
    membership = TeamMembership.create(team_id=EntityId(new_uuid7()), user_id=UserId(new_uuid7()))
    assert membership.team_role == TeamRole.MEMBER
