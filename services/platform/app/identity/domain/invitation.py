"""
Organization Invitation aggregate.

An admin-issued, token-based invite for a specific email address to join
an organization with a specific role — the platform's only member-joining
path other than `register_organization_with_owner`'s org-creation bootstrap
(see organization_management.py's module docstring, which named this exact
gap). Modeled as its own aggregate with recorded events (not a bare token
like EmailVerificationToken/PasswordResetToken) because "who invited whom,
to what role, and what happened to it" is a first-class thing worth an
audit trail of its own, not just a redeem-once secret.

Token lifecycle (expired / already-used / invalid) is intentionally NOT
enforced here, matching EmailVerificationToken/PasswordResetToken: the
application layer (organization_invitations.py) checks expires_at/status
before calling accept(), the same split every other token-based flow in
this context already uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from app.identity.domain.events import (
    OrganizationInvitationAccepted,
    OrganizationInvitationCreated,
    OrganizationInvitationRevoked,
)
from app.identity.domain.value_objects import Email
from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class OrganizationInvitation(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        email: Email,
        role_id: EntityId,
        invited_by_user_id: UserId,
        token_hash: str,
        status: InvitationStatus,
        created_at: datetime,
        expires_at: datetime,
        accepted_at: datetime | None = None,
        revoked_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.email = email
        self.role_id = role_id
        self.invited_by_user_id = invited_by_user_id
        self.token_hash = token_hash
        self.status = status
        self.created_at = created_at
        self.expires_at = expires_at
        self.accepted_at = accepted_at
        self.revoked_at = revoked_at

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        email: Email,
        role_id: EntityId,
        invited_by_user_id: UserId,
        token_hash: str,
        ttl: timedelta = timedelta(days=7),
    ) -> "OrganizationInvitation":
        now = utcnow()
        invitation = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            email=email,
            role_id=role_id,
            invited_by_user_id=invited_by_user_id,
            token_hash=token_hash,
            status=InvitationStatus.PENDING,
            created_at=now,
            expires_at=now + ttl,
        )
        invitation.record_event(
            OrganizationInvitationCreated(
                aggregate_id=invitation.id,
                org_id=org_id,
                email=str(email),
                role_id=role_id,
                invited_by_user_id=invited_by_user_id,
            )
        )
        return invitation

    def is_pending(self) -> bool:
        return self.status == InvitationStatus.PENDING

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at

    def accept(self) -> None:
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = utcnow()
        self.record_event(
            OrganizationInvitationAccepted(aggregate_id=self.id, org_id=self.org_id, email=str(self.email))
        )

    def revoke(self) -> None:
        self.status = InvitationStatus.REVOKED
        self.revoked_at = utcnow()
        self.record_event(OrganizationInvitationRevoked(aggregate_id=self.id, org_id=self.org_id))
