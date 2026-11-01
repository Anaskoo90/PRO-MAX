"""End-to-end regression tests (real Postgres, real seeded roles) for the two
authorization gaps found in the GuildDesk audit:

H1 - suspended/deactivated users kept working sessions and could refresh.
H2 - org_admin could assign itself org_owner; the owner could be demoted.
"""

from __future__ import annotations

import uuid

import pytest
from app.identity.application.rbac_engine import PermissionEvaluator, RoleResolutionService
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.application.user_management import UserManagementService
from app.identity.domain.exceptions import (
    AccountNotActiveError,
    InsufficientAuthorityError,
    OrganizationOwnerProtectedError,
    SessionNotFoundError,
)
from app.identity.domain.rbac import UserRoleAssignment
from app.identity.infrastructure.seed_data import seed_identity
from app.platform_core.errors.api_exceptions import UnauthorizedError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.integration.test_login_flow import (
    _PASSWORD,
    _authenticate_access_token,
    _make_org_and_active_user,
    _make_service,
)
from tests.identity.unit.fakes import FakeAuditRecordSink

pytestmark = pytest.mark.asyncio


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _user_management(uow) -> UserManagementService:
    return UserManagementService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
        file_storage=None,
    )


def _role_service(uow) -> RoleService:
    return RoleService(
        uow_factory=lambda: uow,
        dispatcher=EventDispatcher(),
        permission_catalog=PermissionCatalogService(uow_factory=lambda: uow),
    )


async def _login(uow, org, email):
    return (
        await _make_service(uow).login(
            org_id=OrgId(org.id), email=email, password=_PASSWORD,
            ip_address="127.0.0.1", device_info=None, remember_me=False,
        )
    ).tokens


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_tokens_stop_working_once_the_account_is_suspended_or_deactivated(uow, operation: str) -> None:
    email = f"{_unique('u')}@example.com"
    org, user = await _make_org_and_active_user(uow, slug=_unique("o"), email=email)
    service = _make_service(uow)
    tokens = await _login(uow, org, email)
    await _authenticate_access_token(service, tokens.access_token)  # works before the status change

    management = _user_management(uow)
    if operation == "suspend":
        await management.suspend(
            org_id=OrgId(org.id), user_id=user.id, reason="regression", actor_user_id=UserId(new_uuid7())
        )
    else:
        await management.deactivate_account(user_id=user.id)

    with pytest.raises(UnauthorizedError):
        await _authenticate_access_token(service, tokens.access_token)
    with pytest.raises(SessionNotFoundError):  # session revoked -> refresh token is dead
        await service.refresh(raw_refresh_token=tokens.refresh_token)
    with pytest.raises(AccountNotActiveError):  # and a fresh login is still refused
        await _login(uow, org, email)
    assert await uow.sessions.list_active_for_user(user.id) == []


async def _seeded_org_with_owner_and_admin(uow):
    await seed_identity(uow, extra_permissions=())
    org, owner = await _make_org_and_active_user(uow, slug=_unique("o"), email=f"{_unique('own')}@example.com")
    # make the real user the designated owner, as register_organization_with_owner does
    org.owner_user_id = UserId(owner.id)
    await uow.organizations.update(org)
    admin_role = await uow.roles.get_by_name(None, "org_admin")
    owner_role = await uow.roles.get_by_name(None, "org_owner")
    await uow.user_role_assignments.add(
        UserRoleAssignment.create(user_id=owner.id, role_id=owner_role.id, org_id=OrgId(org.id))
    )
    from app.identity.domain.entities import User
    from app.identity.domain.value_objects import Email

    admin = User.register(
        org_id=OrgId(org.id), email=Email(f"{_unique('adm')}@example.com"), password_hash="hash", display_name="Admin"
    )
    admin.verify_email()
    await uow.users.add(admin)
    await uow.user_role_assignments.add(
        UserRoleAssignment.create(user_id=admin.id, role_id=admin_role.id, org_id=OrgId(org.id))
    )
    await uow.commit()
    return org, owner, admin, owner_role


async def test_seeded_org_admin_cannot_promote_themselves_to_owner(uow) -> None:
    org, _owner, admin, owner_role = await _seeded_org_with_owner_and_admin(uow)
    evaluator = PermissionEvaluator(uow_factory=lambda: uow, role_resolution=RoleResolutionService(uow_factory=lambda: uow))
    assert await evaluator.has_permission(user_id=admin.id, org_id=OrgId(org.id), resource="role", action="assign")

    with pytest.raises(InsufficientAuthorityError):
        await _role_service(uow).assign_role_to_user(
            user_id=admin.id, role_id=owner_role.id, org_id=OrgId(org.id), actor_user_id=admin.id
        )

    assert not await evaluator.has_permission(
        user_id=admin.id, org_id=OrgId(org.id), resource="organization", action="manage_ownership"
    )


async def test_seeded_owner_can_still_assign_the_owner_role(uow) -> None:
    org, owner, admin, owner_role = await _seeded_org_with_owner_and_admin(uow)

    await _role_service(uow).assign_role_to_user(
        user_id=admin.id, role_id=owner_role.id, org_id=OrgId(org.id), actor_user_id=owner.id
    )

    assert await uow.user_role_assignments.get(admin.id, owner_role.id) is not None


async def test_designated_owner_cannot_be_demoted_without_a_transfer(uow) -> None:
    org, owner, _admin, owner_role = await _seeded_org_with_owner_and_admin(uow)

    with pytest.raises(OrganizationOwnerProtectedError):
        await _role_service(uow).revoke_role_from_user(
            user_id=owner.id, role_id=owner_role.id, org_id=OrgId(org.id), actor_user_id=owner.id
        )

    assert await uow.user_role_assignments.get(owner.id, owner_role.id) is not None
