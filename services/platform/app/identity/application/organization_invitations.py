"""
Organization Invitations submodule: the member-joining path
`organization_management.py`'s module docstring flagged as missing —
every organization member other than the owner (created atomically by
`register_organization_with_owner`) now joins by accepting an admin-issued
invitation instead of only via a direct role assignment.

Follows the same token-workflow shape as password_management.py /
email_verification.py: an opaque `secrets.token_urlsafe` value, looked up
by HMAC hash (never stored or logged raw), with expiry/consumption state
checked by this service before the domain aggregate's state-transition
methods are called.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from app.identity.application.dtos import UserProfileDTO
from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.entities import PasswordHistoryEntry, User
from app.identity.domain.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidTokenError,
    InvitationNotFoundError,
    OrganizationNotFoundError,
    RoleNotFoundError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    WeakPasswordError,
)
from app.identity.domain.invitation import OrganizationInvitation
from app.identity.domain.rbac import UserRoleAssignment
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.logger import get_logger
from app.platform_core.notifications.dispatcher import (
    NoProviderRegisteredError,
    NotificationChannel,
    NotificationDispatcher,
    NotificationRequest,
)
from app.platform_core.security.hashing import PasswordHashingService, hash_for_lookup
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY, PasswordPolicy
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId

_logger = get_logger("identity.organization_invitations")

_TOKEN_PEPPER = "change-me-in-production"  # see platform_core.security.secrets_provider


@dataclass(frozen=True, slots=True)
class OrganizationInvitationDTO:
    id: UUID
    org_id: UUID
    email: str
    role_id: UUID
    invited_by_user_id: UUID
    status: str
    created_at: Any
    expires_at: Any


def _to_dto(invitation: OrganizationInvitation) -> OrganizationInvitationDTO:
    return OrganizationInvitationDTO(
        id=invitation.id,
        org_id=invitation.org_id,
        email=str(invitation.email),
        role_id=invitation.role_id,
        invited_by_user_id=invitation.invited_by_user_id,
        status=invitation.status.value,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
    )


class OrganizationInvitationService:
    def __init__(
        self,
        *,
        uow_factory,
        password_hasher: PasswordHashingService,
        notification_dispatcher: NotificationDispatcher,
        dispatcher: EventDispatcher,
        password_policy: PasswordPolicy = DEFAULT_PASSWORD_POLICY,
        invitation_ttl: timedelta = timedelta(days=7),
        invitation_link_base_url: str = "https://app.guilddesk.local/accept-invitation",
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._notification_dispatcher = notification_dispatcher
        self._dispatcher = dispatcher
        self._password_policy = password_policy
        self._invitation_ttl = invitation_ttl
        self._invitation_link_base_url = invitation_link_base_url

    async def invite_member(
        self, *, org_id: OrgId, email: str, role_id: EntityId, invited_by_user_id: UserId
    ) -> OrganizationInvitationDTO:
        normalized_email = Email(email)

        async with self._uow_factory() as uow:
            org = await uow.organizations.get_by_id(EntityId(org_id))
            if org is None:
                raise OrganizationNotFoundError(org_id)

            role = await uow.roles.get_by_id(role_id)
            if role is None or (role.org_id is not None and role.org_id != org_id):
                raise RoleNotFoundError(role_id)

            if await uow.users.get_by_email(org_id, str(normalized_email)) is not None:
                raise EmailAlreadyRegisteredError(str(normalized_email))

            # Superseding an outstanding invite (rather than rejecting the
            # request) matches invalidate_outstanding_for_user's role in
            # password_management.py/email_verification.py: re-inviting the
            # same address is a normal "resend" action, not an error.
            existing = await uow.organization_invitations.get_pending_for_email(org_id, str(normalized_email))
            if existing is not None:
                existing.revoke()
                await uow.organization_invitations.update(existing)

            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER)
            invitation = OrganizationInvitation.create(
                org_id=org_id,
                email=normalized_email,
                role_id=role_id,
                invited_by_user_id=invited_by_user_id,
                token_hash=token_hash,
                ttl=self._invitation_ttl,
            )
            await uow.organization_invitations.add(invitation)
            events = invitation.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id,
                    category=AuditEventCategory.ORGANIZATION_CHANGE,
                    action="organization_invitation_created",
                    actor_user_id=invited_by_user_id,
                    resource_type="organization_invitation",
                    resource_id=str(invitation.id),
                    metadata={"email": str(normalized_email), "role_id": str(role_id)},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

        try:
            await self._notification_dispatcher.dispatch(
                NotificationRequest(
                    org_id=org_id,
                    channel=NotificationChannel.EMAIL,
                    recipient=str(normalized_email),
                    subject=f"You've been invited to join {org.name} on GuildDesk",
                    body=f"{self._invitation_link_base_url}?token={raw_token}",
                )
            )
        except NoProviderRegisteredError:
            # Same graceful degradation as email_verification.py: the
            # invitation is already persisted and can be resent later once
            # a real provider is configured, so this must not fail the
            # request that triggered it.
            await _logger.awarning("invitation_send_skipped_no_provider", invitation_id=str(invitation.id))

        return _to_dto(invitation)

    async def list_pending(self, *, org_id: OrgId, offset: int = 0, limit: int = 50) -> list[OrganizationInvitationDTO]:
        async with self._uow_factory() as uow:
            invitations = await uow.organization_invitations.list_pending_for_org(org_id, offset=offset, limit=limit)
            return [_to_dto(i) for i in invitations]

    async def revoke_invitation(self, *, org_id: OrgId, invitation_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            invitation = await uow.organization_invitations.get_by_id(invitation_id)
            if invitation is None or invitation.org_id != org_id:
                raise InvitationNotFoundError(invitation_id)

            invitation.revoke()
            await uow.organization_invitations.update(invitation)
            events = invitation.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=org_id,
                    category=AuditEventCategory.ORGANIZATION_CHANGE,
                    action="organization_invitation_revoked",
                    actor_user_id=actor_user_id,
                    resource_type="organization_invitation",
                    resource_id=str(invitation.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

    async def accept_invitation(
        self, *, raw_token: str, password: str, display_name: str
    ) -> UserProfileDTO:
        token_hash = hash_for_lookup(raw_token, secret_pepper=_TOKEN_PEPPER)

        violations = self._password_policy.violations(password)
        if violations:
            raise WeakPasswordError(violations)

        async with self._uow_factory() as uow:
            invitation = await uow.organization_invitations.get_by_token_hash(token_hash)
            if invitation is None:
                raise InvalidTokenError("organization_invitation")
            if not invitation.is_pending():
                raise TokenAlreadyUsedError("organization_invitation")
            if invitation.is_expired():
                raise TokenExpiredError("organization_invitation")

            # Re-checked at acceptance time, not just at invite time: the
            # window between the two could be days (invitation_ttl), long
            # enough for the invitee to have registered another way since.
            if await uow.users.get_by_email(invitation.org_id, str(invitation.email)) is not None:
                raise EmailAlreadyRegisteredError(str(invitation.email))

            password_hash = self._password_hasher.hash(password)
            user = User.register(
                org_id=invitation.org_id,
                email=invitation.email,
                password_hash=password_hash,
                display_name=display_name,
            )
            # Accepting a link sent to this exact address is equivalent proof
            # of ownership to an OAuth provider's verified email (see
            # OAuth2LoginService.login_with_callback) - no separate
            # email-verification round-trip needed on top of it.
            user.verify_email()
            await uow.users.add(user)
            await uow.flush()
            await uow.password_history.add(PasswordHistoryEntry.create(user_id=user.id, password_hash=password_hash))
            await uow.user_role_assignments.add(
                UserRoleAssignment.create(user_id=UserId(user.id), role_id=invitation.role_id, org_id=invitation.org_id)
            )

            invitation.accept()
            await uow.organization_invitations.update(invitation)
            events = user.pull_domain_events() + invitation.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=invitation.org_id,
                    category=AuditEventCategory.ORGANIZATION_CHANGE,
                    action="organization_invitation_accepted",
                    actor_user_id=UserId(user.id),
                    resource_type="organization_invitation",
                    resource_id=str(invitation.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)

            return UserProfileDTO(
                id=user.id,
                org_id=user.org_id,
                email=str(user.email),
                display_name=user.display_name,
                status=user.status.value,
                mfa_enabled=user.mfa_enabled,
                avatar_storage_key=user.avatar_storage_key,
                preferences=user.preferences,
            )
