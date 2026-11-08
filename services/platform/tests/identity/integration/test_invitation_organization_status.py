"""Invitation acceptance requires an ACTIVE organization.

An invitation issued before a suspension stays pending but cannot be redeemed
while the organization is suspended or deactivated: acceptance creates no
user, no membership and no role assignment, and leaves the invitation
untouched, so it works again after reactivation. (Real Postgres, seeded roles.)
"""

from __future__ import annotations

import pytest
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.entities import UserStatus
from app.identity.domain.exceptions import OrganizationNotActiveError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId, UserId
from sqlalchemy import text

from tests.identity.integration.test_authorization_regressions import (
    _seeded_org_with_owner_and_admin,
)
from tests.identity.integration.test_invitation_authorization import (
    _PASSWORD,
    _CapturingEmailProvider,
    _email,
    _invitations,
)

pytestmark = pytest.mark.asyncio


def _orgs(uow) -> OrganizationManagementService:
    return OrganizationManagementService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(), dispatcher=EventDispatcher()
    )


async def _pending_invitation(uow, *, tag_email: str | None = None):
    """An organization with a pending invitation (owner -> `member` role)."""
    org, owner, _admin, _owner_role = await _seeded_org_with_owner_and_admin(uow)
    member_role = await uow.roles.get_by_name(None, "member")
    provider = _CapturingEmailProvider()
    email = tag_email or _email()
    await _invitations(uow, provider).invite_member(
        org_id=OrgId(org.id), email=email, role_id=member_role.id, invited_by_user_id=UserId(owner.id)
    )
    return org, owner, member_role, provider, email


async def _accept(uow, provider) -> None:
    await _invitations(uow, provider).accept_invitation(
        raw_token=provider.last_token(), password=_PASSWORD, display_name="Invitee"
    )


async def _assert_nothing_was_created(uow, org, email: str, role) -> None:
    assert await uow.users.get_by_email(OrgId(org.id), email) is None  # no user, hence no membership
    assigned = (
        await uow.session.execute(
            text(
                "SELECT count(*) FROM identity.user_roles ur JOIN identity.users u ON u.id = ur.user_id "
                "WHERE u.org_id = :org AND u.email = :email"
            ),
            {"org": org.id, "email": email},
        )
    ).scalar_one()
    assert assigned == 0  # no role assignment
    pending = await uow.organization_invitations.list_pending_for_org(OrgId(org.id))
    assert len(pending) == 1  # the invitation is untouched, not consumed


@pytest.mark.parametrize("operation", ["suspend", "deactivate"])
async def test_an_invitation_cannot_be_accepted_while_the_organization_is_suspended_or_deactivated(
    uow, operation: str
) -> None:
    org, owner, role, provider, email = await _pending_invitation(uow)
    await getattr(_orgs(uow), operation)(org_id=org.id, actor_user_id=UserId(owner.id))

    with pytest.raises(OrganizationNotActiveError):
        await _accept(uow, provider)

    await _assert_nothing_was_created(uow, org, email, role)


async def test_the_same_invitation_works_again_after_reactivation(uow) -> None:
    org, owner, role, provider, email = await _pending_invitation(uow)
    management = _orgs(uow)
    await management.suspend(org_id=org.id, actor_user_id=UserId(owner.id))
    with pytest.raises(OrganizationNotActiveError):
        await _accept(uow, provider)
    await management.reactivate(org_id=org.id, actor_user_id=UserId(owner.id))

    await _accept(uow, provider)  # the very same token

    member = await uow.users.get_by_email(OrgId(org.id), email)
    assert member is not None and member.status == UserStatus.ACTIVE
    assert await uow.user_role_assignments.get(member.id, role.id) is not None


async def test_acceptance_in_an_active_organization_is_unaffected_by_another_tenants_suspension(uow) -> None:
    suspended_org, suspended_owner, _role, _provider, _email_a = await _pending_invitation(uow)
    healthy_org, _owner, healthy_role, healthy_provider, healthy_email = await _pending_invitation(uow)

    await _orgs(uow).suspend(org_id=suspended_org.id, actor_user_id=UserId(suspended_owner.id))
    await _accept(uow, healthy_provider)

    member = await uow.users.get_by_email(OrgId(healthy_org.id), healthy_email)
    assert member is not None
    assert await uow.user_role_assignments.get(member.id, healthy_role.id) is not None
