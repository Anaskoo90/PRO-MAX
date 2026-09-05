"""
Exercises OrganizationInvitationService end-to-end against the real
database — invite -> accept provisions a new User in the invitation's org
and assigns the invited role, the same "worth covering end-to-end since a
mapper or FK mistake would only surface at integration time" rationale as
test_registration_flow.py.
"""

from __future__ import annotations

import uuid

import secrets

import pytest

from app.identity.application.organization_invitations import OrganizationInvitationService
from app.identity.domain.entities import User, UserStatus
from app.identity.domain.exceptions import EmailAlreadyRegisteredError, InvalidTokenError
from app.identity.domain.invitation import OrganizationInvitation
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import Role
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio

# Must match OrganizationInvitationService's own pepper (same
# "change-me-in-production" placeholder every token-based Identity module
# uses) so a token minted here hashes to what the service looks up.
_TOKEN_PEPPER = "change-me-in-production"


async def _seed_org_owner_and_role(uow) -> tuple[OrgId, EntityId, UserId]:
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    role = Role.create_custom_role(org_id=OrgId(org.id), name="member")
    await uow.roles.add(role)
    await uow.session.flush()

    owner = User(
        id=EntityId(new_uuid7()),
        org_id=OrgId(org.id),
        email=Email(f"owner-{uuid.uuid4().hex[:12]}@example.com"),
        password_hash=PasswordHashingService().hash("Correct-Horse-Battery-9"),
        status=UserStatus.ACTIVE,
        display_name="Owner",
    )
    await uow.users.add(owner)
    # Committed, not just flushed: OrganizationInvitationService opens its
    # own session per call via uow_factory, so this seed data must be
    # durably visible to a session other than the one that wrote it.
    await uow.commit()
    return OrgId(org.id), role.id, UserId(owner.id)


def _service(uow) -> OrganizationInvitationService:
    return OrganizationInvitationService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        notification_dispatcher=NotificationDispatcher(),  # no channel providers wired — dispatch is a no-op skip
        dispatcher=EventDispatcher(),
    )


async def test_invite_then_accept_provisions_user_and_assigns_role(uow) -> None:
    org_id, role_id, owner_id = await _seed_org_owner_and_role(uow)
    email = f"invitee-{uuid.uuid4().hex[:12]}@example.com"

    raw_token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation.create(
        org_id=org_id,
        email=Email(email),
        role_id=role_id,
        invited_by_user_id=owner_id,
        token_hash=hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER),
    )
    await uow.organization_invitations.add(invitation)
    await uow.commit()

    service = _service(uow)
    profile = await service.accept_invitation(raw_token=raw_token, password="Correct-Horse-Battery-9", display_name="Invitee")

    assert profile.org_id == org_id
    assert profile.email == email
    assert profile.status == "active"

    accepted = await uow.organization_invitations.get_by_id(invitation.id)
    assert accepted.status.value == "accepted"

    assignment = await uow.user_role_assignments.get(UserId(profile.id), role_id)
    assert assignment is not None


async def test_accept_invitation_rejects_unknown_token(uow) -> None:
    service = _service(uow)
    with pytest.raises(InvalidTokenError):
        await service.accept_invitation(raw_token="does-not-exist", password="Correct-Horse-Battery-9", display_name="X")


async def test_invite_member_rejects_already_registered_email(uow) -> None:
    org_id, role_id, owner_id = await _seed_org_owner_and_role(uow)
    service = _service(uow)
    owner = await uow.users.get_by_id(EntityId(owner_id))

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.invite_member(
            org_id=org_id, email=str(owner.email), role_id=role_id, invited_by_user_id=owner_id
        )


async def test_invite_member_supersedes_an_outstanding_invitation(uow) -> None:
    org_id, role_id, owner_id = await _seed_org_owner_and_role(uow)
    service = _service(uow)
    email = f"invitee-{uuid.uuid4().hex[:12]}@example.com"

    first = await service.invite_member(org_id=org_id, email=email, role_id=role_id, invited_by_user_id=owner_id)
    second = await service.invite_member(org_id=org_id, email=email, role_id=role_id, invited_by_user_id=owner_id)

    assert first.id != second.id
    superseded = await uow.organization_invitations.get_by_id(first.id)
    assert superseded.status.value == "revoked"
    still_pending = await uow.organization_invitations.get_by_id(second.id)
    assert still_pending.status.value == "pending"


async def test_revoke_invitation_marks_it_revoked(uow) -> None:
    org_id, role_id, owner_id = await _seed_org_owner_and_role(uow)
    service = _service(uow)
    email = f"invitee-{uuid.uuid4().hex[:12]}@example.com"

    invitation = await service.invite_member(org_id=org_id, email=email, role_id=role_id, invited_by_user_id=owner_id)
    await service.revoke_invitation(org_id=org_id, invitation_id=invitation.id, actor_user_id=owner_id)

    revoked = await uow.organization_invitations.get_by_id(invitation.id)
    assert revoked.status.value == "revoked"


async def test_list_pending_returns_the_invite(uow) -> None:
    org_id, role_id, owner_id = await _seed_org_owner_and_role(uow)
    service = _service(uow)
    email = f"invitee-{uuid.uuid4().hex[:12]}@example.com"

    await service.invite_member(org_id=org_id, email=email, role_id=role_id, invited_by_user_id=owner_id)

    pending = await service.list_pending(org_id=org_id)
    assert any(i.email == email for i in pending)
