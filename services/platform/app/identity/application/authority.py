"""Shared "you cannot hand out authority you don't hold yourself" rule.

Used everywhere a user's permissions can grow on someone else's say-so:
role assignment/permission grants/role-parent changes (RoleService) and
member invitations (OrganizationInvitationService, both when an invitation
is issued and when it is redeemed). Keeping a single implementation stops
the paths from drifting apart — an invitation carrying a role is just a
deferred role assignment.
"""

from __future__ import annotations

from uuid import UUID

from app.identity.application.rbac_engine import RoleResolutionService
from app.identity.domain.exceptions import InsufficientAuthorityError
from app.identity.domain.rbac import Role
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


async def effective_permission_ids(uow, role: Role) -> set[EntityId]:
    """Permissions a role grants, including everything inherited up its
    parent chain (the same walk RoleResolutionService performs)."""
    permission_ids: set[EntityId] = set()
    visited: set[EntityId] = set()
    cursor: Role | None = role
    while cursor is not None and cursor.id not in visited:
        visited.add(cursor.id)
        permission_ids |= cursor.permission_ids
        cursor = (
            await uow.roles.get_by_id(cursor.parent_role_id)
            if cursor.parent_role_id is not None
            else None
        )
    return permission_ids


async def assert_actor_holds(
    uow, *, actor_user_id: UUID, org_id: OrgId, required: set[EntityId], action: str
) -> None:
    """Raise InsufficientAuthorityError unless the actor's own effective
    permissions in `org_id` cover everything in `required`."""
    if not required:
        return
    resolution = RoleResolutionService(uow_factory=lambda: uow)
    actor_roles = await resolution.resolve_effective_roles(
        uow=uow, user_id=UserId(actor_user_id), org_id=org_id
    )
    held: set[EntityId] = set()
    for actor_role in actor_roles:
        held |= actor_role.permission_ids
    if not required <= held:
        raise InsufficientAuthorityError(action)
