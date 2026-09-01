from datetime import timedelta

from app.identity.domain.events import (
    OrganizationInvitationAccepted,
    OrganizationInvitationCreated,
    OrganizationInvitationRevoked,
)
from app.identity.domain.invitation import InvitationStatus, OrganizationInvitation
from app.identity.domain.value_objects import Email
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7


def _invitation(**overrides) -> OrganizationInvitation:
    defaults = dict(
        org_id=OrgId(new_uuid7()),
        email=Email("invitee@example.com"),
        role_id=EntityId(new_uuid7()),
        invited_by_user_id=UserId(new_uuid7()),
        token_hash="hashed-token",
    )
    defaults.update(overrides)
    return OrganizationInvitation.create(**defaults)


def test_create_records_organization_invitation_created_event() -> None:
    invitation = _invitation()

    assert invitation.status == InvitationStatus.PENDING
    assert invitation.is_pending()
    assert not invitation.is_expired()
    events = invitation.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], OrganizationInvitationCreated)
    assert events[0].email == "invitee@example.com"


def test_create_defaults_to_a_seven_day_expiry() -> None:
    invitation = _invitation()
    assert invitation.expires_at - invitation.created_at == timedelta(days=7)


def test_accept_transitions_status_and_records_event() -> None:
    invitation = _invitation()
    invitation.pull_domain_events()

    invitation.accept()

    assert invitation.status == InvitationStatus.ACCEPTED
    assert not invitation.is_pending()
    assert invitation.accepted_at is not None
    events = invitation.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], OrganizationInvitationAccepted)


def test_revoke_transitions_status_and_records_event() -> None:
    invitation = _invitation()
    invitation.pull_domain_events()

    invitation.revoke()

    assert invitation.status == InvitationStatus.REVOKED
    assert not invitation.is_pending()
    assert invitation.revoked_at is not None
    events = invitation.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], OrganizationInvitationRevoked)


def test_is_expired_reflects_ttl() -> None:
    invitation = _invitation(ttl=timedelta(seconds=-1))
    assert invitation.is_expired()
