"""
RBAC Engine: role resolution, permission evaluation, policy evaluation.

Role hierarchy is inheritance-by-permission-union: a role with a
parent_role_id inherits every permission its ancestors grant, walked here
rather than denormalized into role_permissions at write time — keeps
grant/revoke on a parent role instantly reflected in every descendant
without a fan-out write.
"""

from __future__ import annotations

from app.identity.application.ports import IdentityUnitOfWorkPort
from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.exceptions import InsufficientPermissionError
from app.identity.domain.rbac import Role
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class RoleResolutionService:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def resolve_effective_roles(self, *, uow: IdentityUnitOfWorkPort, user_id: UserId, org_id: OrgId) -> list[Role]:
        assignments = await uow.user_role_assignments.list_for_user(user_id, org_id)
        roles: dict[EntityId, Role] = {}
        for assignment in assignments:
            role = await uow.roles.get_by_id(assignment.role_id)
            if role is not None:
                await self._collect_with_ancestors(uow, role, roles)
        return list(roles.values())

    async def _collect_with_ancestors(self, uow: IdentityUnitOfWorkPort, role: Role, collected: dict[EntityId, Role]) -> None:
        if role.id in collected:
            return
        collected[role.id] = role
        if role.parent_role_id is not None:
            parent = await uow.roles.get_by_id(role.parent_role_id)
            if parent is not None:
                await self._collect_with_ancestors(uow, parent, collected)


class PermissionEvaluator:
    def __init__(self, *, uow_factory, role_resolution: RoleResolutionService) -> None:
        self._uow_factory = uow_factory
        self._role_resolution = role_resolution

    async def has_permission(self, *, user_id: UserId, org_id: OrgId, resource: str, action: str) -> bool:
        async with self._uow_factory() as uow:
            permission = await uow.permissions.get_by_key(resource, action)
            if permission is None:
                return False
            roles = await self._role_resolution.resolve_effective_roles(uow=uow, user_id=user_id, org_id=org_id)
            granted_permission_ids: set[EntityId] = set()
            for role in roles:
                granted_permission_ids |= role.permission_ids
            return permission.id in granted_permission_ids

    async def assert_permission(self, *, user_id: UserId, org_id: OrgId, resource: str, action: str) -> None:
        if not await self.has_permission(user_id=user_id, org_id=org_id, resource=resource, action=action):
            async with self._uow_factory() as uow:
                await uow.audit_logs.add(
                    AuditLogRecord.create(
                        org_id=org_id,
                        category=AuditEventCategory.AUTHORIZATION,
                        action="permission_denied",
                        actor_user_id=user_id,
                        resource_type=resource,
                        resource_id=action,
                    )
                )
                await uow.commit()
            raise InsufficientPermissionError(resource, action)


class PolicyEvaluator:
    """A named policy is currently just a required-permission shorthand
    (`"resource:action"`); this is the seam a future attribute-based
    condition (e.g. "only within own team") would extend without changing
    every call site that currently checks a bare permission."""

    def __init__(self, *, permission_evaluator: PermissionEvaluator) -> None:
        self._permission_evaluator = permission_evaluator

    async def evaluate(self, *, user_id: UserId, org_id: OrgId, policy: str) -> bool:
        resource, _, action = policy.partition(":")
        return await self._permission_evaluator.has_permission(
            user_id=user_id, org_id=org_id, resource=resource, action=action
        )
