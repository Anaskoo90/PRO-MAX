"""
Roles + Permissions submodules.

RoleService owns Role CRUD, role hierarchy, and role assignment/revocation
to users. PermissionCatalogService owns the read-only Permission Catalog
(seeded via infrastructure/seed_data.py, never created ad hoc through the
API) plus permission validation — RoleService delegates to it rather than
duplicating the "does this permission exist" check.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.exceptions import (
    PermissionNotFoundError,
    RoleAlreadyExistsError,
    RoleHierarchyCycleError,
    RoleNotFoundError,
    UserNotFoundError,
)
from app.identity.domain.rbac import Role, UserRoleAssignment
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


@dataclass(frozen=True, slots=True)
class RoleDTO:
    id: UUID
    org_id: UUID | None
    name: str
    description: str
    is_system_role: bool
    parent_role_id: UUID | None
    permission_ids: list[UUID]


@dataclass(frozen=True, slots=True)
class PermissionDTO:
    id: UUID
    resource: str
    action: str
    description: str


def _role_to_dto(role: Role) -> RoleDTO:
    return RoleDTO(
        id=role.id, org_id=role.org_id, name=role.name, description=role.description,
        is_system_role=role.is_system_role, parent_role_id=role.parent_role_id,
        permission_ids=list(role.permission_ids),
    )


class PermissionCatalogService:
    def __init__(self, *, uow_factory) -> None:
        self._uow_factory = uow_factory

    async def list_catalog(self) -> list[PermissionDTO]:
        async with self._uow_factory() as uow:
            permissions = await uow.permissions.list_all()
            return [PermissionDTO(id=p.id, resource=p.resource, action=p.action, description=p.description) for p in permissions]

    async def validate_exists(self, uow, *, permission_id: EntityId) -> None:
        permission = await uow.permissions.get_by_id(permission_id)
        if permission is None:
            raise PermissionNotFoundError(permission_id)


class RoleService:
    def __init__(self, *, uow_factory, dispatcher: EventDispatcher, permission_catalog: PermissionCatalogService) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._permission_catalog = permission_catalog

    async def create_custom_role(
        self, *, org_id: OrgId, name: str, description: str = "", actor_user_id: UUID
    ) -> RoleDTO:
        async with self._uow_factory() as uow:
            if await uow.roles.get_by_name(org_id, name) is not None:
                raise RoleAlreadyExistsError(name)
            role = Role.create_custom_role(org_id=org_id, name=name, description=description)
            await uow.roles.add(role)
            events = role.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_created",
                    actor_user_id=actor_user_id, resource_type="role", resource_id=str(role.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def update_role(self, *, role_id: EntityId, name: str | None, actor_user_id: UUID) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await uow.roles.get_by_id(role_id)
            if role is None:
                raise RoleNotFoundError(role_id)
            if name is not None:
                role.rename(name)
            await uow.roles.update(role)
            events = role.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=role.org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_updated",
                    actor_user_id=actor_user_id, resource_type="role", resource_id=str(role.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def set_parent(self, *, role_id: EntityId, parent_role_id: EntityId | None) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await uow.roles.get_by_id(role_id)
            if role is None:
                raise RoleNotFoundError(role_id)
            if parent_role_id is not None:
                cursor: EntityId | None = parent_role_id
                visited: set[EntityId] = set()
                while cursor is not None:
                    if cursor == role_id:
                        raise RoleHierarchyCycleError()
                    if cursor in visited:
                        break
                    visited.add(cursor)
                    ancestor = await uow.roles.get_by_id(cursor)
                    cursor = ancestor.parent_role_id if ancestor else None
            role.set_parent(parent_role_id)
            await uow.roles.update(role)
            events = role.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def delete_role(self, *, role_id: EntityId, actor_user_id: UUID) -> None:
        async with self._uow_factory() as uow:
            role = await uow.roles.get_by_id(role_id)
            if role is None:
                raise RoleNotFoundError(role_id)
            role.mark_deleted()
            events = role.pull_domain_events()
            await uow.roles.delete(role_id)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=role.org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_deleted",
                    actor_user_id=actor_user_id, resource_type="role", resource_id=str(role.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def grant_permission(self, *, role_id: EntityId, permission_id: EntityId, actor_user_id: UUID) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await uow.roles.get_by_id(role_id)
            if role is None:
                raise RoleNotFoundError(role_id)
            await self._permission_catalog.validate_exists(uow, permission_id=permission_id)
            role.grant_permission(permission_id)
            await uow.roles.update(role)
            events = role.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=role.org_id, category=AuditEventCategory.PERMISSION_CHANGE, action="permission_granted_to_role",
                    actor_user_id=actor_user_id, resource_type="role", resource_id=str(role.id),
                    metadata={"permission_id": str(permission_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def revoke_permission(self, *, role_id: EntityId, permission_id: EntityId, actor_user_id: UUID) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await uow.roles.get_by_id(role_id)
            if role is None:
                raise RoleNotFoundError(role_id)
            role.revoke_permission(permission_id)
            await uow.roles.update(role)
            events = role.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=role.org_id, category=AuditEventCategory.PERMISSION_CHANGE, action="permission_revoked_from_role",
                    actor_user_id=actor_user_id, resource_type="role", resource_id=str(role.id),
                    metadata={"permission_id": str(permission_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def assign_role_to_user(self, *, user_id: UserId, role_id: EntityId, org_id: OrgId, actor_user_id: UUID) -> None:
        async with self._uow_factory() as uow:
            role = await uow.roles.get_by_id(role_id)
            # A role from a *different* organization's custom-role set must
            # be just as invalid a target as one that doesn't exist at all —
            # otherwise an org_admin could assign another tenant's custom
            # role to one of their own users purely by guessing its id.
            # System roles (org_id is None) are shared across every org, so
            # those are always a valid target.
            if role is None or (role.org_id is not None and role.org_id != org_id):
                raise RoleNotFoundError(role_id)

            user = await uow.users.get_by_id(EntityId(user_id))
            # Likewise, the target user must actually belong to the caller's
            # org — without this, org_id on the new UserRoleAssignment row
            # would silently disagree with the user's real organization.
            if user is None or user.org_id != org_id:
                raise UserNotFoundError(user_id)

            if await uow.user_role_assignments.get(user_id, role_id) is not None:
                return
            await uow.user_role_assignments.add(UserRoleAssignment.create(user_id=user_id, role_id=role_id, org_id=org_id))
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_assigned_to_user",
                    actor_user_id=actor_user_id, resource_type="user", resource_id=str(user_id),
                    metadata={"role_id": str(role_id)},
                )
            )
            await uow.commit()

    async def revoke_role_from_user(self, *, user_id: UserId, role_id: EntityId, org_id: OrgId, actor_user_id: UUID) -> None:
        async with self._uow_factory() as uow:
            assignment = await uow.user_role_assignments.get(user_id, role_id)
            if assignment is None or assignment.org_id != org_id:
                return
            await uow.user_role_assignments.delete(assignment.id)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_revoked_from_user",
                    actor_user_id=actor_user_id, resource_type="user", resource_id=str(user_id),
                    metadata={"role_id": str(role_id)},
                )
            )
            await uow.commit()

    async def list_roles_for_org(self, *, org_id: OrgId) -> list[RoleDTO]:
        async with self._uow_factory() as uow:
            system_roles = await uow.roles.list_system_roles()
            org_roles = await uow.roles.list_for_org(org_id)
            return [_role_to_dto(r) for r in (*system_roles, *org_roles)]

    async def list_roles_for_user(self, *, user_id: UserId, org_id: OrgId) -> list[RoleDTO]:
        """The other direction of assign/revoke — lets the dashboard show a
        member's *current* roles before toggling them, rather than the
        Roles page having to blindly re-derive that from assign/revoke
        calls that already succeeded."""
        async with self._uow_factory() as uow:
            assignments = await uow.user_role_assignments.list_for_user(user_id, org_id)
            roles = [await uow.roles.get_by_id(a.role_id) for a in assignments]
            return [_role_to_dto(r) for r in roles if r is not None]
