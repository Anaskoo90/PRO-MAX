"""
In-memory fakes satisfying the Identity repository Protocols
(app.identity.domain.repositories) — used to unit-test application-layer
services (RBAC Engine, etc.) without a real database, since the Protocols
are structural and any object with matching methods satisfies them.
"""

from __future__ import annotations

from app.identity.domain.rbac import Permission, Role, UserRoleAssignment
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class FakeRoleRepository:
    def __init__(self) -> None:
        self.roles: dict[EntityId, Role] = {}

    async def get_by_id(self, role_id: EntityId) -> Role | None:
        return self.roles.get(role_id)

    async def get_by_name(self, org_id: OrgId | None, name: str) -> Role | None:
        return next((r for r in self.roles.values() if r.org_id == org_id and r.name == name), None)

    async def list_system_roles(self) -> list[Role]:
        return [r for r in self.roles.values() if r.is_system_role]

    async def list_for_org(self, org_id: OrgId) -> list[Role]:
        return [r for r in self.roles.values() if r.org_id == org_id]

    async def add(self, role: Role) -> None:
        self.roles[role.id] = role

    async def update(self, role: Role) -> None:
        self.roles[role.id] = role

    async def delete(self, role_id: EntityId) -> None:
        self.roles.pop(role_id, None)


class FakePermissionRepository:
    def __init__(self) -> None:
        self.permissions: dict[EntityId, Permission] = {}

    async def get_by_id(self, permission_id: EntityId) -> Permission | None:
        return self.permissions.get(permission_id)

    async def get_by_key(self, resource: str, action: str) -> Permission | None:
        return next((p for p in self.permissions.values() if p.resource == resource and p.action == action), None)

    async def list_all(self) -> list[Permission]:
        return list(self.permissions.values())

    async def add(self, permission: Permission) -> None:
        self.permissions[permission.id] = permission


class FakeUserRoleAssignmentRepository:
    def __init__(self) -> None:
        self.assignments: list[UserRoleAssignment] = []

    async def list_for_user(self, user_id: UserId, org_id: OrgId) -> list[UserRoleAssignment]:
        return [a for a in self.assignments if a.user_id == user_id and a.org_id == org_id]

    async def get(self, user_id: UserId, role_id: EntityId) -> UserRoleAssignment | None:
        return next((a for a in self.assignments if a.user_id == user_id and a.role_id == role_id), None)

    async def add(self, assignment: UserRoleAssignment) -> None:
        self.assignments.append(assignment)

    async def delete(self, assignment_id: EntityId) -> None:
        self.assignments = [a for a in self.assignments if a.id != assignment_id]


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.records: list = []

    async def add(self, record) -> None:
        self.records.append(record)

    async def list_for_org(self, org_id, *, category=None, limit: int = 50):
        results = [r for r in self.records if r.org_id == org_id]
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:limit]


class FakeUnitOfWork:
    """Satisfies IdentityUnitOfWorkPort for the repositories a given test
    actually exercises; unused attributes are left None deliberately, so a
    test that touches one accidentally gets a clear AttributeError rather
    than silently succeeding against an empty fake."""

    def __init__(self, *, roles=None, permissions=None, user_role_assignments=None, audit_logs=None) -> None:
        self.roles = roles or FakeRoleRepository()
        self.permissions = permissions or FakePermissionRepository()
        self.user_role_assignments = user_role_assignments or FakeUserRoleAssignmentRepository()
        self.audit_logs = audit_logs or FakeAuditLogRepository()

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None
