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

from app.identity.application.dtos import UserProfileDTO, user_to_profile_dto
from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.entities import PasswordHistoryEntry, User, UserStatus
from app.identity.domain.exceptions import (
    OrganizationNotFoundError,
    OrganizationSlugTakenError,
    UserNotFoundError,
    WeakPasswordError,
)
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import UserRoleAssignment
from app.identity.domain.value_objects import Email
from app.platform_core.api.sorting import SortField
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY, PasswordPolicy
from app.platform_core.shared_kernel.dtos import PagedResult
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
    description: str | None
    logo_url: str | None


def _to_dto(org: Organization) -> OrganizationDTO:
    return OrganizationDTO(
        id=org.id, name=org.name, slug=org.slug, owner_user_id=org.owner_user_id, status=org.status.value,
        settings=org.settings, description=org.description, logo_url=org.logo_url,
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

            # Flushed between each dependent add: org/user/password_history/
            # user_role_assignments have real FK chains (users.org_id ->
            # organizations.id, password_history.user_id -> users.id), but
            # the ORM models have no relationship() between them by design
            # (see identity/infrastructure/orm_models.py), so SQLAlchemy
            # won't auto-order these INSERTs within a single flush.
            await uow.organizations.add(org)
            await uow.flush()
            await uow.users.add(owner)
            await uow.flush()
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

    async def update(
        self, *, org_id: EntityId, name: str | None, actor_user_id: UUID,
        slug: str | None = None, description: str | None = None, logo_url: str | None = None,
    ) -> OrganizationDTO:
        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(org_id)
            if org is None:
                raise OrganizationNotFoundError(org_id)

            changed_fields: list[str] = []
            if name is not None:
                org.rename(name)
                changed_fields.append("name")
            if slug is not None and slug != org.slug:
                existing = await uow.organizations.get_by_slug(slug)
                if existing is not None and existing.id != org.id:
                    raise OrganizationSlugTakenError(slug)
                org.change_slug(slug)
                changed_fields.append("slug")
            if description is not None:
                org.update_description(description)
                changed_fields.append("description")
            if logo_url is not None:
                org.update_logo_url(logo_url)
                changed_fields.append("logo_url")

            await uow.organizations.update(org)
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org.id, category=AuditEventCategory.ORGANIZATION_CHANGE, action="organization_updated",
                    actor_user_id=actor_user_id, resource_type="organization", resource_id=str(org.id),
                    metadata={"changed_fields": changed_fields},
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

    async def search_members(
        self, *, org_id: OrgId, query: str | None = None, status: str | None = None,
        sort: list[SortField] | None = None, page: int = 1, page_size: int = 50,
    ) -> PagedResult[UserProfileDTO]:
        """The dashboard's member-listing endpoint — same data as
        list_members, plus free-text search, a status filter, sort, and a
        real total count for pagination UI (list_members has none of
        those; kept as-is rather than folded into this, same reasoning as
        Ticket System's list_for_org/search_for_org split in Phase 2A)."""
        async with self._uow_factory() as uow:
            users, total = await uow.users.search(
                org_id, query=query, status=status, sort=sort, offset=(page - 1) * page_size, limit=page_size,
            )
            return PagedResult(items=[user_to_profile_dto(u) for u in users], total=total, page=page, page_size=page_size)

    async def get_member(self, *, org_id: OrgId, user_id: EntityId) -> UserProfileDTO:
        """Member-detail lookup, scoped to the requesting admin's own org —
        a member id that resolves to a *different* org's user is treated
        as not-found rather than 403, so this endpoint never confirms or
        denies another organization's user IDs exist."""
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None or user.org_id != org_id:
                raise UserNotFoundError(user_id)
            return user_to_profile_dto(user)

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
