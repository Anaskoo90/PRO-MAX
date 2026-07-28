"""
RBAC domain: Role, Permission, and their assignment join entities.

System roles: org_id is None, is_system_role is True — seeded at startup,
immutable (SystemRoleImmutableError), shared across every organization.
Organization/custom roles: org_id is set, is_system_role is False. This two-
dimensional model covers "System Roles" / "Organization Roles" / "Custom
Roles" without a third table — an org-scoped role *is* a custom role; there
is no separate "predefined but org-scoped" tier requested anywhere in the
platform's actual RBAC needs.
"""

from __future__ import annotations

from app.identity.domain.events import (
    PermissionAssignedToRole,
    PermissionRevokedFromRole,
    RoleAssignedToUser,
    RoleCreated,
    RoleDeleted,
    RoleRevokedFromUser,
    RoleUpdated,
)
from app.identity.domain.exceptions import SystemRoleImmutableError
from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


class Permission:
    """Reference entity — rows come from the seeded PERMISSION_CATALOG
    (infrastructure/seed_data.py), never created ad hoc through the API."""

    def __init__(self, *, id: EntityId, resource: str, action: str, description: str) -> None:
        self.id = id
        self.resource = resource
        self.action = action
        self.description = description

    @property
    def key(self) -> str:
        return f"{self.resource}:{self.action}"

    @classmethod
    def create(cls, *, resource: str, action: str, description: str) -> "Permission":
        return cls(id=EntityId(new_uuid7()), resource=resource, action=action, description=description)


class Role(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId | None,
        name: str,
        description: str,
        is_system_role: bool,
        parent_role_id: EntityId | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.name = name
        self.description = description
        self.is_system_role = is_system_role
        self.parent_role_id = parent_role_id
        self.version = version
        self.permission_ids: set[EntityId] = set()

    @classmethod
    def create_system_role(cls, *, name: str, description: str) -> "Role":
        role = cls(
            id=EntityId(new_uuid7()), org_id=None, name=name, description=description, is_system_role=True
        )
        role.record_event(RoleCreated(aggregate_id=role.id, org_id=None, name=name, is_system_role=True))
        return role

    @classmethod
    def create_custom_role(
        cls, *, org_id: OrgId, name: str, description: str = "", parent_role_id: EntityId | None = None
    ) -> "Role":
        role = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            name=name,
            description=description,
            is_system_role=False,
            parent_role_id=parent_role_id,
        )
        role.record_event(RoleCreated(aggregate_id=role.id, org_id=org_id, name=name, is_system_role=False))
        return role

    def _assert_mutable(self) -> None:
        if self.is_system_role:
            raise SystemRoleImmutableError(self.name)

    def rename(self, name: str) -> None:
        self._assert_mutable()
        self.name = name
        self.record_event(RoleUpdated(aggregate_id=self.id))

    def set_parent(self, parent_role_id: EntityId | None) -> None:
        self._assert_mutable()
        self.parent_role_id = parent_role_id
        self.record_event(RoleUpdated(aggregate_id=self.id))

    def grant_permission(self, permission_id: EntityId) -> None:
        self._assert_mutable()
        self.permission_ids.add(permission_id)
        self.record_event(PermissionAssignedToRole(aggregate_id=self.id, permission_id=permission_id))

    def grant_permission_during_bootstrap(self, permission_id: EntityId) -> None:
        """Bootstrap-only counterpart to grant_permission, called exclusively
        by seed_identity() (infrastructure/seed_data.py) to establish and grow
        a system role's permission set as new bounded contexts register their
        own permissions into the shared catalog over time.

        Deliberately bypasses _assert_mutable(): a system role's *contents*
        (its granted permissions) are expected to grow at bootstrap time as
        the platform grows — org_owner/org_admin are documented as covering
        "every resource, including ones contexts introduce later" — but its
        identity and structure must never change through the public API.
        rename/set_parent/grant_permission/revoke_permission/mark_deleted all
        remain fully blocked for system roles via _assert_mutable(); this
        method does not touch that guard, it is a distinct, narrowly-scoped
        operation that only the trusted bootstrap process can reach (it is
        never wired into RoleService or any HTTP route). That distinction —
        "the bootstrap process extended a system role's grants" versus "a
        user modified a system role" — is exactly the invariant this class
        exists to protect, so it's modeled as its own named domain operation
        rather than a conditional bypass on the general-purpose method."""
        self.permission_ids.add(permission_id)
        self.record_event(PermissionAssignedToRole(aggregate_id=self.id, permission_id=permission_id))

    def revoke_permission(self, permission_id: EntityId) -> None:
        self._assert_mutable()
        self.permission_ids.discard(permission_id)
        self.record_event(PermissionRevokedFromRole(aggregate_id=self.id, permission_id=permission_id))

    def mark_deleted(self) -> None:
        self._assert_mutable()
        self.record_event(RoleDeleted(aggregate_id=self.id))


class UserRoleAssignment:
    """Hard-deletable join entity (identity.user_roles, per the original
    Physical Database Schema)."""

    def __init__(self, *, id: EntityId, user_id: UserId, role_id: EntityId, org_id: OrgId) -> None:
        self.id = id
        self.user_id = user_id
        self.role_id = role_id
        self.org_id = org_id

    @classmethod
    def create(cls, *, user_id: UserId, role_id: EntityId, org_id: OrgId) -> "UserRoleAssignment":
        return cls(id=EntityId(new_uuid7()), user_id=user_id, role_id=role_id, org_id=org_id)


def role_assigned_event(user_id: UserId, role_id: EntityId) -> RoleAssignedToUser:
    return RoleAssignedToUser(aggregate_id=EntityId(user_id), user_id=user_id, role_id=role_id)


def role_revoked_event(user_id: UserId, role_id: EntityId) -> RoleRevokedFromUser:
    return RoleRevokedFromUser(aggregate_id=EntityId(user_id), user_id=user_id, role_id=role_id)
