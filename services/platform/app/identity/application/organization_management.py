"""
Organization Management submodule: create, update, settings, ownership,
members, status.

`register_organization_with_owner` is the platform's actual bootstrap
entry point — resolves the chicken-and-egg between Organization (needs an
owner_user_id) and User (needs an org_id, NOT NULL) by pre-generating both
UUIDv7 ids and creating both aggregates in one transaction, rather than a
two-request flow. This is also the only supported way to create an
organization: there is still no separate user-invitation flow (standing
gap, restated from the Platform Administrator Guide) — every other member
joins via an admin-issued role assignment after the org exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.entities import PasswordHistoryEntry, User, UserStatus
from app.identity.domain.exceptions import (
    OrganizationNotFoundError,
    OrganizationSlugTakenError,
    WeakPasswordError,
)
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import UserRoleAssignment
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY, PasswordPolicy
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


@dataclass(frozen=True, slots=True)
class OrganizationDTO:
    id: UUID
    name: str
    slug: str
    owner_user_id: UUID
    status: str
    settings: dict[str, Any]


def _to_dto(org: Organization) -> OrganizationDTO:
    return OrganizationDTO(
        id=org.id, name=org.name, slug=org.slug, owner_user_id=org.owner_user_id, status=org.status.value,
        settings=org.settings,
    )


class OrganizationManagementService:
    def __init__(
        self,
        *,
        uow_factory,
        password_hasher: PasswordHashingService,
        dispatcher: EventDispatcher,
        password_policy: PasswordPolicy = DEFAULT_PASSWORD_POLICY,
        owner_system_role_name: str = "org_owner",
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._dispatcher = dispatcher
        self._password_policy = password_policy
        self._owner_system_role_name = owner_system_role_name

    async def register_organization_with_owner(
        self, *, org_name: str, slug: str, owner_email: str, owner_password: str, owner_display_name: str
    ) -> tuple[OrganizationDTO, UUID]:
        violations = self._password_policy.violations(owner_password)
        if violations:
            raise WeakPasswordError(violations)

        async with self._uow_factory() as uow:
            if await uow.organizations.get_by_slug(slug) is not None:
                raise OrganizationSlugTakenError(slug)

            owner_user_id = UserId(new_uuid7())
            org = Organization.create(name=org_name, slug=slug, owner_user_id=owner_user_id)

            password_hash = self._password_hasher.hash(owner_password)
            owner = User(
                id=EntityId(owner_user_id),
                org_id=OrgId(org.id),
                email=Email(owner_email),
                password_hash=password_hash,
                status=UserStatus.PENDING_VERIFICATION,
                display_name=owner_display_name,
            )

            await uow.organizations.add(org)
            await uow.users.add(owner)
            await uow.password_history.add(PasswordHistoryEntry.create(user_id=owner.id, password_hash=password_hash))

            owner_role = await uow.roles.get_by_name(None, self._owner_system_role_name)
            if owner_role is not None:
                await uow.user_role_assignments.add(
                    UserRoleAssignment.create(user_id=owner_user_id, role_id=owner_role.id, org_id=OrgId(org.id))
                )

            events = org.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org.id, category=AuditEventCategory.ORGANIZATION_CHANGE, action="organization_created",
                    actor_user_id=owner_user_id, resource_type="organization", resource_id=str(org.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(org), owner.id

    async def get(self, *, org_id: EntityId) -> OrganizationDTO:
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
            if org is None:
                raise OrganizationNotFoundError(org_id)
            return _to_dto(org)

    async def update(self, *, org_id: EntityId, name: str | None, actor_user_id: UUID) -> OrganizationDTO:
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
            if org is None:
                raise OrganizationNotFoundError(org_id)
            if name is not None:
                org.rename(name)
            await uow.organizations.update(org)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org.id, category=AuditEventCategory.ORGANIZATION_CHANGE, action="organization_updated",
                    actor_user_id=actor_user_id, resource_type="organization", resource_id=str(org.id),
                )
            )
            await uow.commit()
            return _to_dto(org)

    async def update_settings(self, *, org_id: EntityId, patch: dict[str, Any], actor_user_id: UUID) -> OrganizationDTO:
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
            if org is None:
                raise OrganizationNotFoundError(org_id)
            org.update_settings(patch)
            await uow.organizations.update(org)
            events = org.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org.id, category=AuditEventCategory.ORGANIZATION_CHANGE, action="organization_settings_updated",
                    actor_user_id=actor_user_id, resource_type="organization", resource_id=str(org.id),
                    metadata={"changed_keys": list(patch.keys())},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(org)

    async def transfer_ownership(self, *, org_id: EntityId, new_owner_user_id: UUID, actor_user_id: UUID) -> OrganizationDTO:
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
            if org is None:
                raise OrganizationNotFoundError(org_id)
            org.transfer_ownership(UserId(new_owner_user_id))
            await uow.organizations.update(org)

            owner_role = await uow.roles.get_by_name(None, self._owner_system_role_name)
            if owner_role is not None and await uow.user_role_assignments.get(UserId(new_owner_user_id), owner_role.id) is None:
                await uow.user_role_assignments.add(
                    UserRoleAssignment.create(user_id=UserId(new_owner_user_id), role_id=owner_role.id, org_id=OrgId(org.id))
                )

            events = org.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org.id, category=AuditEventCategory.ORGANIZATION_CHANGE, action="ownership_transferred",
                    actor_user_id=actor_user_id, resource_type="organization", resource_id=str(org.id),
                    metadata={"new_owner_user_id": str(new_owner_user_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(org)

    async def list_members(self, *, org_id: OrgId, offset: int = 0, limit: int = 50):
        async with self._uow_factory() as uow:
            return await uow.users.list_by_org(org_id, offset=offset, limit=limit)

    async def _set_status(self, *, org_id: EntityId, action: str, transition, actor_user_id: UUID) -> OrganizationDTO:
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
            if org is None:
                raise OrganizationNotFoundError(org_id)
            transition(org)
            await uow.organizations.update(org)
            events = org.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org.id, category=AuditEventCategory.ORGANIZATION_CHANGE, action=action,
                    actor_user_id=actor_user_id, resource_type="organization", resource_id=str(org.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(org)

    async def suspend(self, *, org_id: EntityId, actor_user_id: UUID) -> OrganizationDTO:
        return await self._set_status(org_id=org_id, action="organization_suspended", transition=Organization.suspend, actor_user_id=actor_user_id)

    async def reactivate(self, *, org_id: EntityId, actor_user_id: UUID) -> OrganizationDTO:
        return await self._set_status(org_id=org_id, action="organization_reactivated", transition=Organization.reactivate, actor_user_id=actor_user_id)

    async def deactivate(self, *, org_id: EntityId, actor_user_id: UUID) -> OrganizationDTO:
        return await self._set_status(org_id=org_id, action="organization_deactivated", transition=Organization.deactivate, actor_user_id=actor_user_id)
