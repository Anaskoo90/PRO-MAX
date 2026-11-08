"""Invitation authorization (Milestone 2 of the H1/H2 follow-up).

An invitation is a deferred role assignment. It must obey the same
"no authority beyond your own" rule when issued, and the inviter must still
be active and still authorized when it is redeemed.
"""

from __future__ import annotations

import uuid

import pytest
from app.identity.application.organization_invitations import OrganizationInvitationService
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.application.user_management import UserManagementService
from app.identity.domain.exceptions import (
    InsufficientAuthorityError,
    InvitationNoLongerValidError,
    RoleInUseError,
)
from app.identity.domain.rbac import Role
from app.platform_core.errors.handlers import _map_status_code
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId, UserId

from tests.identity.integration.test_authorization_regressions import (
    _seeded_org_with_owner_and_admin,
)
from tests.identity.unit.fakes import FakeAuditRecordSink

pytestmark = pytest.mark.asyncio

_PEPPER = "test-token-pepper-with-at-least-32-characters"
_PASSWORD = "Correct-Horse-Battery-9"


class _CapturingEmailProvider:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, message) -> None:
        self.messages.append(message)

    def last_token(self) -> str:
        body = self.messages[-1].html_body or self.messages[-1].text_body
        return body.split("token=")[1].split('"')[0].split("<")[0].split()[0]


def _invitations(uow, email_provider: _CapturingEmailProvider) -> OrganizationInvitationService:
    return OrganizationInvitationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        notification_dispatcher=NotificationDispatcher(email_provider=email_provider),
        dispatcher=EventDispatcher(),
        token_pepper=_PEPPER,
    )


def _roles(uow) -> RoleService:
    return RoleService(
        uow_factory=lambda: uow,
        dispatcher=EventDispatcher(),
        permission_catalog=PermissionCatalogService(uow_factory=lambda: uow),
    )


def _users(uow) -> UserManagementService:
    return UserManagementService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
        file_storage=None,
    )


def _email() -> str:
    return f"invitee-{uuid.uuid4().hex[:10]}@example.com"


async def _accept(uow, provider) -> None:
    await _invitations(uow, provider).accept_invitation(
        raw_token=provider.last_token(), password=_PASSWORD, display_name="Invitee"
    )


# ---- creation-time authority --------------------------------------------------------


async def test_org_admin_cannot_invite_someone_as_org_owner(uow) -> None:
    org, _owner, admin, owner_role = await _seeded_org_with_owner_and_admin(uow)
    provider = _CapturingEmailProvider()

    with pytest.raises(InsufficientAuthorityError):
        await _invitations(uow, provider).invite_member(
            org_id=OrgId(org.id), email=_email(), role_id=owner_role.id, invited_by_user_id=UserId(admin.id)
        )

    assert provider.messages == []  # nothing was issued or mailed
    assert await uow.organization_invitations.list_pending_for_org(OrgId(org.id)) == []


async def test_org_owner_can_invite_someone_as_org_owner(uow) -> None:
    org, owner, _admin, owner_role = await _seeded_org_with_owner_and_admin(uow)
    provider = _CapturingEmailProvider()

    await _invitations(uow, provider).invite_member(
        org_id=OrgId(org.id), email=_email(), role_id=owner_role.id, invited_by_user_id=UserId(owner.id)
    )
    await _accept(uow, provider)  # redeemed while the owner is still authorized


async def test_org_admin_can_invite_into_a_role_within_their_own_authority(uow) -> None:
    org, _owner, admin, _owner_role = await _seeded_org_with_owner_and_admin(uow)
    admin_role = await uow.roles.get_by_name(None, "org_admin")
    provider = _CapturingEmailProvider()

    await _invitations(uow, provider).invite_member(
        org_id=OrgId(org.id), email=_email(), role_id=admin_role.id, invited_by_user_id=UserId(admin.id)
    )
    await _accept(uow, provider)


# ---- redemption-time re-validation --------------------------------------------------


async def _admin_invites_into_admin_role(uow):
    org, owner, admin, _owner_role = await _seeded_org_with_owner_and_admin(uow)
    admin_role = await uow.roles.get_by_name(None, "org_admin")
    provider = _CapturingEmailProvider()
    await _invitations(uow, provider).invite_member(
        org_id=OrgId(org.id), email=_email(), role_id=admin_role.id, invited_by_user_id=UserId(admin.id)
    )
    return org, owner, admin, admin_role, provider


async def _assert_invitation_not_redeemed(uow, org, provider) -> None:
    with pytest.raises(InvitationNoLongerValidError):
        await _accept(uow, provider)
    # still pending (not consumed) and no account was provisioned
    assert len(await uow.organization_invitations.list_pending_for_org(OrgId(org.id))) == 1
    invitee_email = provider.messages[-1].to_address
    assert await uow.users.get_by_email(OrgId(org.id), invitee_email) is None


async def test_invitation_cannot_be_redeemed_after_the_inviter_is_suspended(uow) -> None:
    org, owner, admin, _role, provider = await _admin_invites_into_admin_role(uow)
    await _users(uow).suspend(
        org_id=OrgId(org.id), user_id=admin.id, reason="rogue admin", actor_user_id=UserId(owner.id)
    )

    await _assert_invitation_not_redeemed(uow, org, provider)


async def test_invitation_cannot_be_redeemed_after_the_inviter_is_deactivated(uow) -> None:
    org, _owner, admin, _role, provider = await _admin_invites_into_admin_role(uow)
    await _users(uow).deactivate_account(user_id=admin.id)

    await _assert_invitation_not_redeemed(uow, org, provider)


async def test_invitation_cannot_be_redeemed_after_the_inviter_is_demoted(uow) -> None:
    org, owner, admin, admin_role, provider = await _admin_invites_into_admin_role(uow)
    await _roles(uow).revoke_role_from_user(
        user_id=admin.id, role_id=admin_role.id, org_id=OrgId(org.id), actor_user_id=owner.id
    )

    await _assert_invitation_not_redeemed(uow, org, provider)


async def test_invitation_cannot_be_redeemed_if_the_role_outgrew_the_inviters_authority(uow) -> None:
    org, _owner, admin, _owner_role = await _seeded_org_with_owner_and_admin(uow)
    org_id = OrgId(org.id)
    custom = Role.create_custom_role(org_id=org_id, name="support")
    await uow.roles.add(custom)
    await uow.commit()
    provider = _CapturingEmailProvider()
    await _invitations(uow, provider).invite_member(
        org_id=org_id, email=_email(), role_id=custom.id, invited_by_user_id=UserId(admin.id)
    )
    # After the invitation was issued the role gains a permission the (admin)
    # inviter does not hold: organization:manage_ownership is owner-only.
    manage_ownership = next(
        p for p in await uow.permissions.list_all() if (p.resource, p.action) == ("organization", "manage_ownership")
    )
    custom.grant_permission(manage_ownership.id)
    await uow.roles.update(custom)
    await uow.commit()

    await _assert_invitation_not_redeemed(uow, org, provider)


# ---- role deletion ------------------------------------------------------------------


async def test_deleting_a_role_referenced_by_a_pending_invitation_is_a_409_conflict(uow) -> None:
    org, owner, _admin, _owner_role = await _seeded_org_with_owner_and_admin(uow)
    org_id = OrgId(org.id)
    custom = Role.create_custom_role(org_id=org_id, name="temp-role")
    await uow.roles.add(custom)
    await uow.commit()
    await _invitations(uow, _CapturingEmailProvider()).invite_member(
        org_id=org_id, email=_email(), role_id=custom.id, invited_by_user_id=UserId(owner.id)
    )

    with pytest.raises(RoleInUseError) as excinfo:
        await _roles(uow).delete_role(org_id=org_id, role_id=custom.id, actor_user_id=owner.id)

    assert _map_status_code(excinfo.value) == 409
    assert await uow.roles.get_by_id(custom.id) is not None  # role untouched


async def test_an_unreferenced_role_can_still_be_deleted(uow) -> None:
    org, owner, _admin, _owner_role = await _seeded_org_with_owner_and_admin(uow)
    org_id = OrgId(org.id)
    custom = Role.create_custom_role(org_id=org_id, name="disposable")
    await uow.roles.add(custom)
    await uow.commit()

    await _roles(uow).delete_role(org_id=org_id, role_id=custom.id, actor_user_id=owner.id)

    assert await uow.roles.get_by_id(custom.id) is None
