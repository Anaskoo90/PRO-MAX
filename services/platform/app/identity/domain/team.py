"""Team aggregate: create/update/delete, membership, hierarchy."""

from __future__ import annotations

from enum import StrEnum

from app.identity.domain.events import (
    TeamCreated,
    TeamDeleted,
    TeamMemberAdded,
    TeamMemberRemoved,
    TeamUpdated,
)
from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class TeamRole(StrEnum):
    LEAD = "lead"
    MEMBER = "member"


class Team(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        name: str,
        description: str,
        parent_team_id: EntityId | None,
        is_deleted: bool = False,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.name = name
        self.description = description
        self.parent_team_id = parent_team_id
        self.is_deleted = is_deleted
        self.version = version

    @classmethod
    def create(
        cls, *, org_id: OrgId, name: str, description: str = "", parent_team_id: EntityId | None = None
    ) -> "Team":
        team = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            name=name,
            description=description,
            parent_team_id=parent_team_id,
        )
        team.record_event(TeamCreated(aggregate_id=team.id, org_id=org_id, name=name))
        return team

    def update(self, *, name: str | None = None, description: str | None = None) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        self.record_event(TeamUpdated(aggregate_id=self.id))

    def set_parent(self, parent_team_id: EntityId | None) -> None:
        self.parent_team_id = parent_team_id
        self.record_event(TeamUpdated(aggregate_id=self.id))

    def delete(self) -> None:
        self.is_deleted = True
        self.record_event(TeamDeleted(aggregate_id=self.id))


class TeamMembership:
    """Hard-deletable join entity — same established exception as
    project_members/user_roles/staff_server_assignments elsewhere in the
    platform's persistence conventions."""

    def __init__(self, *, id: EntityId, team_id: EntityId, user_id: UserId, team_role: TeamRole, joined_at=None) -> None:
        self.id = id
        self.team_id = team_id
        self.user_id = user_id
        self.team_role = team_role
        self.joined_at = joined_at or utcnow()

    @classmethod
    def create(cls, *, team_id: EntityId, user_id: UserId, team_role: TeamRole = TeamRole.MEMBER) -> "TeamMembership":
        return cls(id=EntityId(new_uuid7()), team_id=team_id, user_id=user_id, team_role=team_role)


def build_team_ancestry_chain(team_id: EntityId, teams_by_id: dict[EntityId, Team]) -> list[EntityId]:
    """Walks parent_team_id pointers to detect a cycle before it's written —
    called by the application layer before persisting a new parent_team_id,
    since the domain entity alone can't see sibling aggregates."""
    chain: list[EntityId] = []
    current = teams_by_id.get(team_id)
    seen: set[EntityId] = set()
    while current is not None and current.parent_team_id is not None:
        if current.parent_team_id in seen:
            raise RuntimeError("Cycle detected while walking team hierarchy")
        seen.add(current.parent_team_id)
        chain.append(current.parent_team_id)
        current = teams_by_id.get(current.parent_team_id)
    return chain
