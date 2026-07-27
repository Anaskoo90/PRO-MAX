"""Identity domain events — in-process only (platform_core.events.contracts.DomainEvent).
Integration-event mapping (for org-wide/cross-context consumers, e.g. Notification
Center reacting to UserRegistered) is registered in identity/composition.py via
an IntegrationEventMapperRegistry, not here."""

from __future__ import annotations

from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class UserRegistered(DomainEvent):
    event_type = "identity.user_registered"
    org_id: UUID
    email: str


class UserEmailVerified(DomainEvent):
    event_type = "identity.user_email_verified"
    email: str


class UserLoggedIn(DomainEvent):
    event_type = "identity.user_logged_in"
    session_id: UUID


class UserLoggedOut(DomainEvent):
    event_type = "identity.user_logged_out"
    session_id: UUID


class UserSuspended(DomainEvent):
    event_type = "identity.user_suspended"
    reason: str


class UserReactivated(DomainEvent):
    event_type = "identity.user_reactivated"


class PasswordChanged(DomainEvent):
    event_type = "identity.password_changed"


class PasswordResetRequested(DomainEvent):
    event_type = "identity.password_reset_requested"


class MfaEnabled(DomainEvent):
    event_type = "identity.mfa_enabled"
    factor_type: str


class MfaDisabled(DomainEvent):
    event_type = "identity.mfa_disabled"
    factor_type: str


class SessionRevoked(DomainEvent):
    event_type = "identity.session_revoked"
    session_id: UUID


class SuspiciousLoginDetected(DomainEvent):
    event_type = "identity.suspicious_login_detected"
    session_id: UUID
    ip_address: str


# --- Organization -----------------------------------------------------------


class OrganizationCreated(DomainEvent):
    event_type = "identity.organization_created"
    name: str
    slug: str
    owner_user_id: UUID


class OrganizationSettingsUpdated(DomainEvent):
    event_type = "identity.organization_settings_updated"
    changed_keys: list[str]


class OrganizationOwnershipTransferred(DomainEvent):
    event_type = "identity.organization_ownership_transferred"
    previous_owner_user_id: UUID
    new_owner_user_id: UUID


class OrganizationStatusChanged(DomainEvent):
    event_type = "identity.organization_status_changed"
    status: str


# --- Team ---------------------------------------------------------------


class TeamCreated(DomainEvent):
    event_type = "identity.team_created"
    org_id: UUID
    name: str


class TeamUpdated(DomainEvent):
    event_type = "identity.team_updated"


class TeamDeleted(DomainEvent):
    event_type = "identity.team_deleted"


class TeamMemberAdded(DomainEvent):
    event_type = "identity.team_member_added"
    user_id: UUID
    team_role: str


class TeamMemberRemoved(DomainEvent):
    event_type = "identity.team_member_removed"
    user_id: UUID


# --- RBAC -----------------------------------------------------------------


class RoleCreated(DomainEvent):
    event_type = "identity.role_created"
    org_id: UUID | None
    name: str
    is_system_role: bool


class RoleUpdated(DomainEvent):
    event_type = "identity.role_updated"


class RoleDeleted(DomainEvent):
    event_type = "identity.role_deleted"


class PermissionAssignedToRole(DomainEvent):
    event_type = "identity.permission_assigned_to_role"
    permission_id: UUID


class PermissionRevokedFromRole(DomainEvent):
    event_type = "identity.permission_revoked_from_role"
    permission_id: UUID


class RoleAssignedToUser(DomainEvent):
    event_type = "identity.role_assigned_to_user"
    user_id: UUID
    role_id: UUID


class RoleRevokedFromUser(DomainEvent):
    event_type = "identity.role_revoked_from_user"
    user_id: UUID
    role_id: UUID
