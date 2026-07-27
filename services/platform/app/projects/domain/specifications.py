"""Projects & Workspaces specifications, per the Domain Modeling & DDD
Blueprint's Specification pattern (shared_kernel.validation.Specification)."""

from __future__ import annotations

from app.platform_core.shared_kernel.validation import Specification
from app.projects.domain.entities import MembershipStatus, ProjectMembership, ProjectRole


class ProjectMemberHasRoleSpecification(Specification[ProjectMembership]):
    def __init__(self, *allowed_roles: ProjectRole) -> None:
        self._allowed_roles = frozenset(allowed_roles)

    def is_satisfied_by(self, candidate: ProjectMembership) -> bool:
        return candidate.status == MembershipStatus.ACTIVE and candidate.role in self._allowed_roles


CAN_MANAGE_PROJECT = ProjectMemberHasRoleSpecification(ProjectRole.OWNER, ProjectRole.ADMIN)
CAN_CONTRIBUTE_TO_PROJECT = ProjectMemberHasRoleSpecification(
    ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.CONTRIBUTOR
)
