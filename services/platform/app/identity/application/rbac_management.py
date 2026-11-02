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

from app.identity.application import authority
from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.exceptions import (
    OrganizationOwnerProtectedError,
    PermissionNotFoundError,
    RoleAlreadyExistsError,
    RoleHierarchyCycleError,
    RoleInUseError,
    RoleNotFoundError,
    UserNotFoundError,
)
from app.identity.domain.rbac import (
    Role,
    UserRoleAssignment,
    role_assigned_event,
    role_revoked_event,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.events.integration_event import append_domain_events_to_outbox
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


# Name of the seeded system role (seed_data.py) that carries organization
# ownership; the organization's designated owner must always hold it.
_OWNER_ROLE_NAME = "org_owner"


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
            await append_domain_events_to_outbox(uow.outbox, events, org_id=role.org_id)
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def update_role(
        self,
        *,
        org_id: OrgId,
        role_id: EntityId,
        name: str | None,
        actor_user_id: UUID,
    ) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await self._get_mutable_role_for_org(
                uow, role_id=role_id, org_id=org_id
            )
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
            await append_domain_events_to_outbox(uow.outbox, events, org_id=role.org_id)
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def set_parent(
        self,
        *,
        org_id: OrgId,
        role_id: EntityId,
        parent_role_id: EntityId | None,
        actor_user_id: UUID,
    ) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await self._get_mutable_role_for_org(
                uow, role_id=role_id, org_id=org_id
            )
            if parent_role_id is not None:
                cursor: EntityId | None = parent_role_id
                visited: set[EntityId] = set()
                inherited_permission_ids: set[EntityId] = set()
                while cursor is not None:
                    if cursor == role_id:
                        raise RoleHierarchyCycleError()
                    if cursor in visited:
                        break
                    visited.add(cursor)
                    ancestor = await uow.roles.get_by_id(cursor)
                    if ancestor is None or (
                        ancestor.org_id is not None and ancestor.org_id != org_id
                    ):
                        raise RoleNotFoundError(cursor)
                    inherited_permission_ids |= ancestor.permission_ids
                    cursor = ancestor.parent_role_id
                # Inheriting a parent hands this role (and its holders) every
                # permission up the chain, so the actor must hold them all.
                await self._assert_actor_holds(
                    uow, actor_user_id=actor_user_id, org_id=org_id,
                    required=inherited_permission_ids, action="set a parent role",
                )
            role.set_parent(parent_role_id)
            await uow.roles.update(role)
            events = role.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id,
                    category=AuditEventCategory.ROLE_CHANGE,
                    action="role_parent_updated",
                    actor_user_id=actor_user_id,
                    resource_type="role",
                    resource_id=str(role.id),
                    metadata={
                        "parent_role_id": (
                            str(parent_role_id) if parent_role_id is not None else None
                        )
                    },
                )
            )
            await append_domain_events_to_outbox(uow.outbox, events, org_id=role.org_id)
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def delete_role(
        self, *, org_id: OrgId, role_id: EntityId, actor_user_id: UUID
    ) -> None:
        async with self._uow_factory() as uow:
            role = await self._get_mutable_role_for_org(
                uow, role_id=role_id, org_id=org_id
            )
            # organization_invitations.role_id is a hard FK, so deleting a role
            # an invitation still points at would surface as a raw database
            # IntegrityError (HTTP 500). Report it as the conflict it is.
            if await uow.organization_invitations.exists_for_role(role_id):
                raise RoleInUseError(role_id)
            role.mark_deleted()
            events = role.pull_domain_events()
            await uow.roles.delete(role_id)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=role.org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_deleted",
                    actor_user_id=actor_user_id, resource_type="role", resource_id=str(role.id),
                )
            )
            await append_domain_events_to_outbox(uow.outbox, events, org_id=role.org_id)
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def grant_permission(
        self,
        *,
        org_id: OrgId,
        role_id: EntityId,
        permission_id: EntityId,
        actor_user_id: UUID,
    ) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await self._get_mutable_role_for_org(
                uow, role_id=role_id, org_id=org_id
            )
            await self._permission_catalog.validate_exists(uow, permission_id=permission_id)
            await self._assert_actor_holds(
                uow, actor_user_id=actor_user_id, org_id=org_id,
                required={permission_id}, action="grant a permission",
            )
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
            await append_domain_events_to_outbox(uow.outbox, events, org_id=role.org_id)
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _role_to_dto(role)

    async def revoke_permission(
        self,
        *,
        org_id: OrgId,
        role_id: EntityId,
        permission_id: EntityId,
        actor_user_id: UUID,
    ) -> RoleDTO:
        async with self._uow_factory() as uow:
            role = await self._get_mutable_role_for_org(
                uow, role_id=role_id, org_id=org_id
            )
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
            await append_domain_events_to_outbox(uow.outbox, events, org_id=role.org_id)
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

            # No handing out authority the actor doesn't hold themselves —
            # this is also what keeps org_admin (which lacks
            # organization:manage_ownership) from assigning org_owner.
            await self._assert_actor_holds(
                uow, actor_user_id=actor_user_id, org_id=org_id,
                required=await self._effective_permission_ids(uow, role),
                action="assign a role",
            )

            if await uow.user_role_assignments.get(user_id, role_id) is not None:
                return
            assignment = UserRoleAssignment.create(
                user_id=user_id, role_id=role_id, org_id=org_id
            )
            await uow.user_role_assignments.add(assignment)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_assigned_to_user",
                    actor_user_id=actor_user_id, resource_type="user", resource_id=str(user_id),
                    metadata={"role_id": str(role_id)},
                )
            )
            event = role_assigned_event(user_id, role_id)
            await append_domain_events_to_outbox(
                uow.outbox, [event], org_id=assignment.org_id
            )
            await uow.commit()
            await self._dispatcher.dispatch(event)

    async def revoke_role_from_user(self, *, user_id: UserId, role_id: EntityId, org_id: OrgId, actor_user_id: UUID) -> None:
        async with self._uow_factory() as uow:
            assignment = await uow.user_role_assignments.get(user_id, role_id)
            if assignment is None or assignment.org_id != org_id:
                return
            role = await uow.roles.get_by_id(role_id)
            if role is not None:
                # The designated owner can't be demoted until ownership has
                # been transferred through the dedicated flow.
                if role.is_system_role and role.name == _OWNER_ROLE_NAME:
                    org = await uow.organizations.get_by_id(org_id)
                    if org is not None and org.owner_user_id == user_id:
                        raise OrganizationOwnerProtectedError("remove the owner role from")
                # Likewise you can't strip a role you couldn't have assigned.
                await self._assert_actor_holds(
                    uow, actor_user_id=actor_user_id, org_id=org_id,
                    required=await self._effective_permission_ids(uow, role),
                    action="revoke a role",
                )
            await uow.user_role_assignments.delete(assignment.id)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id, category=AuditEventCategory.ROLE_CHANGE, action="role_revoked_from_user",
                    actor_user_id=actor_user_id, resource_type="user", resource_id=str(user_id),
                    metadata={"role_id": str(role_id)},
                )
            )
            event = role_revoked_event(user_id, role_id)
            await append_domain_events_to_outbox(
                uow.outbox, [event], org_id=assignment.org_id
            )
            await uow.commit()
            await self._dispatcher.dispatch(event)

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

    @staticmethod
    async def _effective_permission_ids(uow, role: Role) -> set[EntityId]:
        return await authority.effective_permission_ids(uow, role)

    async def _assert_actor_holds(
        self, uow, *, actor_user_id: UUID, org_id: OrgId, required: set[EntityId], action: str
    ) -> None:
        await authority.assert_actor_holds(
            uow, actor_user_id=actor_user_id, org_id=org_id, required=required, action=action
        )

    @staticmethod
    async def _get_mutable_role_for_org(
        uow, *, role_id: EntityId, org_id: OrgId
    ) -> Role:
        role = await uow.roles.get_by_id(role_id)
        if role is None or role.org_id != org_id:
            raise RoleNotFoundError(role_id)
        return role
