"""Identity-specific domain exceptions, layered on platform_core's exception
hierarchy so the global handler (platform_core.errors.handlers) maps them
without any Identity-specific handler registration."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import (
    BusinessRuleViolationError,
    DomainError,
    EntityNotFoundError,
)
from app.platform_core.shared_kernel.error_codes import ErrorCode


class InvalidCredentialsError(BusinessRuleViolationError):
    code = ErrorCode.UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("invalid_credentials", "Email or password is incorrect")


class AccountLockedError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "account_locked",
            f"Account is temporarily locked; retry after {retry_after_seconds}s",
        )
        self.retry_after_seconds = retry_after_seconds


class AccountNotActiveError(BusinessRuleViolationError):
    def __init__(self, status: str) -> None:
        super().__init__("account_not_active", f"Account status '{status}' does not permit login")


class EmailAlreadyRegisteredError(BusinessRuleViolationError):
    def __init__(self, email: str) -> None:
        super().__init__("email_already_registered", f"'{email}' is already registered")


class EmailAlreadyVerifiedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("email_already_verified", "Email address is already verified")


class TokenExpiredError(BusinessRuleViolationError):
    def __init__(self, token_kind: str) -> None:
        super().__init__("token_expired", f"{token_kind} token has expired")


class TokenAlreadyUsedError(BusinessRuleViolationError):
    def __init__(self, token_kind: str) -> None:
        super().__init__("token_already_used", f"{token_kind} token was already used")


class InvalidTokenError(BusinessRuleViolationError):
    def __init__(self, token_kind: str) -> None:
        super().__init__("invalid_token", f"{token_kind} token is invalid")


class WeakPasswordError(BusinessRuleViolationError):
    def __init__(self, violations: list[str]) -> None:
        super().__init__("weak_password", "; ".join(violations))
        self.violations = violations


class PasswordReuseError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "password_reuse", "This password was used recently; choose a different one"
        )


class MfaRequiredError(BusinessRuleViolationError):
    code = ErrorCode.UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("mfa_required", "Multi-factor verification is required to continue")


class InvalidMfaCodeError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("invalid_mfa_code", "The provided MFA code is invalid")


class MfaAlreadyEnrolledError(BusinessRuleViolationError):
    def __init__(self, factor_type: str) -> None:
        super().__init__("mfa_already_enrolled", f"'{factor_type}' is already enrolled")


class RecoveryCodeAlreadyUsedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("recovery_code_used", "This recovery code has already been used")


class UserNotFoundError(EntityNotFoundError):
    def __init__(self, user_id: object) -> None:
        super().__init__("User", user_id)


class AvatarNotFoundError(EntityNotFoundError):
    def __init__(self, user_id: object) -> None:
        super().__init__("Avatar", user_id)


class InvalidAvatarError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_avatar", reason)


class SessionNotFoundError(EntityNotFoundError):
    def __init__(self, session_id: object) -> None:
        super().__init__("Session", session_id)


class OAuthProviderNotConfiguredError(EntityNotFoundError):
    def __init__(self, provider_key: str) -> None:
        super().__init__("OAuthProvider", provider_key)


# --- Organization -----------------------------------------------------------


class InvalidOrganizationSlugError(BusinessRuleViolationError):
    def __init__(self, slug: str) -> None:
        super().__init__("invalid_organization_slug", f"'{slug}' is not a valid organization slug")


class OrganizationSlugTakenError(BusinessRuleViolationError):
    def __init__(self, slug: str) -> None:
        super().__init__("organization_slug_taken", f"Slug '{slug}' is already in use")


class OrganizationNotFoundError(EntityNotFoundError):
    def __init__(self, org_id: object) -> None:
        super().__init__("Organization", org_id)


class OrganizationNotActiveError(BusinessRuleViolationError):
    """Raised by AuthenticationService when a member of a suspended or
    deactivated organization tries to log in, refresh a session or complete
    MFA (HTTP 422, like AccountNotActiveError for a suspended user)."""

    def __init__(self, status: str) -> None:
        super().__init__("organization_not_active", f"Organization status '{status}' does not permit this action")


# --- Organization Invitation -------------------------------------------


class InvitationNotFoundError(EntityNotFoundError):
    def __init__(self, invitation_id: object) -> None:
        super().__init__("OrganizationInvitation", invitation_id)


# --- Team ---------------------------------------------------------------


class TeamNotFoundError(EntityNotFoundError):
    def __init__(self, team_id: object) -> None:
        super().__init__("Team", team_id)


class TeamHierarchyCycleError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("team_hierarchy_cycle", "This would create a cycle in the team hierarchy")


class TeamMembershipNotFoundError(EntityNotFoundError):
    def __init__(self, team_id: object, user_id: object) -> None:
        super().__init__("TeamMembership", f"{team_id}:{user_id}")


# --- RBAC -----------------------------------------------------------------


class RoleNotFoundError(EntityNotFoundError):
    def __init__(self, role_id: object) -> None:
        super().__init__("Role", role_id)


class RoleInUseError(BusinessRuleViolationError):
    """A role cannot be deleted while other records (currently: organization
    invitations) still reference it. Mapped to HTTP 409."""

    code = ErrorCode.CONFLICT

    def __init__(self, role_id: object) -> None:
        super().__init__(
            "role_in_use",
            "Role is still referenced by one or more invitations and cannot be deleted",
        )
        self.role_id = role_id


class InvitationNoLongerValidError(BusinessRuleViolationError):
    """The invitation can no longer be redeemed because the inviter is no
    longer active or no longer authorized to grant the invited role. The
    message is deliberately generic: the invitee is not entitled to details
    about the inviter's account or the organization's role configuration."""

    def __init__(self) -> None:
        super().__init__("invitation_no_longer_valid", "This invitation can no longer be accepted")


class NotOrganizationOwnerError(BusinessRuleViolationError):
    """Only the organization's designated owner may hand ownership over;
    holding the org_owner role alone (e.g. as a co-owner or a former owner)
    is not enough."""

    code = ErrorCode.FORBIDDEN

    def __init__(self) -> None:
        super().__init__(
            "not_organization_owner", "Only the organization owner can transfer ownership"
        )


class InvalidOwnershipTransferTargetError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        messages = {
            "not_active": "The new owner must be an active member of the organization",
            "already_owner": "That user already owns the organization",
        }
        super().__init__("invalid_ownership_transfer_target", messages[reason])
        self.reason = reason


class OwnerRoleNotConfiguredError(DomainError):
    """The seeded owner system role is missing. This is a deployment/seed
    problem, not a client error, so it maps to HTTP 500 and is logged with a
    traceback; operations that would leave an owner without the role refuse to
    run instead of silently continuing."""

    code = ErrorCode.INTERNAL_ERROR

    def __init__(self, role_name: str) -> None:
        super().__init__(f"Organization owner role '{role_name}' is not configured")
        self.role_name = role_name


class RoleAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self, name: str) -> None:
        super().__init__("role_already_exists", f"A role named '{name}' already exists")


class SystemRoleImmutableError(BusinessRuleViolationError):
    def __init__(self, role_name: str) -> None:
        super().__init__("system_role_immutable", f"System role '{role_name}' cannot be modified or deleted")


class RoleHierarchyCycleError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("role_hierarchy_cycle", "This would create a cycle in the role hierarchy")


class PermissionNotFoundError(EntityNotFoundError):
    def __init__(self, permission_id: object) -> None:
        super().__init__("Permission", permission_id)


class PermissionNotInCatalogError(BusinessRuleViolationError):
    def __init__(self, resource: str, action: str) -> None:
        super().__init__(
            "permission_not_in_catalog", f"'{resource}:{action}' is not a recognized permission"
        )


class InsufficientPermissionError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, resource: str, action: str) -> None:
        super().__init__("insufficient_permission", f"Missing permission '{resource}:{action}'")
        self.resource = resource
        self.action = action


class InsufficientAuthorityError(BusinessRuleViolationError):
    """Raised when an actor tries to hand out authority they do not hold
    themselves (assigning a role, granting a permission, or inheriting a
    parent role whose permissions exceed their own)."""

    code = ErrorCode.FORBIDDEN

    def __init__(self, action: str) -> None:
        super().__init__(
            "insufficient_authority", f"Cannot {action} beyond your own permissions"
        )
        self.action = action


class OrganizationOwnerProtectedError(BusinessRuleViolationError):
    """Raised when an operation would remove or demote the organization's
    designated owner; ownership must be transferred first."""

    def __init__(self, action: str) -> None:
        super().__init__(
            "organization_owner_protected",
            f"Cannot {action} the organization owner; transfer ownership first",
        )
        self.action = action


# --- Security ---------------------------------------------------------------


class IpAddressRestrictedError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, ip_address: str) -> None:
        super().__init__("ip_address_restricted", f"Access from '{ip_address}' is not permitted for this organization")


class BruteForceProtectionTriggeredError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "brute_force_protection_triggered",
            f"Too many attempts from this source; retry after {retry_after_seconds}s",
        )
        self.retry_after_seconds = retry_after_seconds
