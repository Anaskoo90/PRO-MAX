import uuid

import pytest

from app.identity.domain.entities import User, UserStatus
from app.identity.domain.invitation import OrganizationInvitation
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import Role
from app.identity.domain.value_objects import Email
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def _seed_org_and_role(uow) -> tuple[OrgId, EntityId, UserId]:
    # Flushed between each dependent add, same as
    # OrganizationManagementService.register_organization_with_owner: these
    # ORM models have no relationship() cascades, so SQLAlchemy won't
    # auto-order cross-table INSERTs within a single flush.
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    role = Role.create_custom_role(org_id=OrgId(org.id), name="member")
    await uow.roles.add(role)
    await uow.session.flush()

    inviter = User(
        id=EntityId(new_uuid7()),
        org_id=OrgId(org.id),
        email=Email(f"inviter-{uuid.uuid4().hex[:12]}@example.com"),
        password_hash=PasswordHashingService().hash("Correct-Horse-Battery-9"),
        status=UserStatus.ACTIVE,
        display_name="Inviter",
    )
    await uow.users.add(inviter)
    await uow.session.flush()
    return OrgId(org.id), role.id, UserId(inviter.id)


async def test_add_then_get_by_id_round_trips(uow) -> None:
    org_id, role_id, inviter_id = await _seed_org_and_role(uow)
    invitation = OrganizationInvitation.create(
        org_id=org_id,
        email=Email(f"invitee-{uuid.uuid4().hex[:12]}@example.com"),
        role_id=role_id,
        invited_by_user_id=inviter_id,
        token_hash="hashed-token",
    )
    await uow.organization_invitations.add(invitation)
    await uow.session.flush()

    fetched = await uow.organization_invitations.get_by_id(invitation.id)

    assert fetched is not None
    assert str(fetched.email) == str(invitation.email)
    assert fetched.status == invitation.status


async def test_get_by_token_hash_finds_the_invitation(uow) -> None:
    org_id, role_id, inviter_id = await _seed_org_and_role(uow)
    invitation = OrganizationInvitation.create(
        org_id=org_id,
        email=Email(f"invitee-{uuid.uuid4().hex[:12]}@example.com"),
        role_id=role_id,
        invited_by_user_id=inviter_id,
        token_hash="a-unique-token-hash",
    )
    await uow.organization_invitations.add(invitation)
    await uow.session.flush()

    fetched = await uow.organization_invitations.get_by_token_hash("a-unique-token-hash")

    assert fetched is not None
    assert fetched.id == invitation.id


async def test_get_pending_for_email_ignores_accepted_invitations(uow) -> None:
    org_id, role_id, inviter_id = await _seed_org_and_role(uow)
    email = f"invitee-{uuid.uuid4().hex[:12]}@example.com"
    invitation = OrganizationInvitation.create(
        org_id=org_id, email=Email(email), role_id=role_id, invited_by_user_id=inviter_id, token_hash="tok-1"
    )
    await uow.organization_invitations.add(invitation)
    await uow.session.flush()

    assert await uow.organization_invitations.get_pending_for_email(org_id, email) is not None

    invitation.accept()
    await uow.organization_invitations.update(invitation)
    await uow.session.flush()

    assert await uow.organization_invitations.get_pending_for_email(org_id, email) is None


async def test_list_pending_for_org_excludes_revoked(uow) -> None:
    org_id, role_id, inviter_id = await _seed_org_and_role(uow)
    pending = OrganizationInvitation.create(
        org_id=org_id,
        email=Email(f"pending-{uuid.uuid4().hex[:12]}@example.com"),
        role_id=role_id,
        invited_by_user_id=inviter_id,
        token_hash="tok-pending",
    )
    revoked = OrganizationInvitation.create(
        org_id=org_id,
        email=Email(f"revoked-{uuid.uuid4().hex[:12]}@example.com"),
        role_id=role_id,
        invited_by_user_id=inviter_id,
        token_hash="tok-revoked",
    )
    revoked.revoke()
    await uow.organization_invitations.add(pending)
    await uow.organization_invitations.add(revoked)
    await uow.session.flush()

    listed = await uow.organization_invitations.list_pending_for_org(org_id)

    listed_ids = {i.id for i in listed}
    assert pending.id in listed_ids
    assert revoked.id not in listed_ids
