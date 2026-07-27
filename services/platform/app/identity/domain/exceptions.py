"""Identity-specific domain exceptions, layered on platform_core's exception
hierarchy so the global handler (platform_core.errors.handlers) maps them
without any Identity-specific handler registration."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError, EntityNotFoundError
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


class SessionNotFoundError(EntityNotFoundError):
    def __init__(self, session_id: object) -> None:
        super().__init__("Session", session_id)


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
    def __init__(self, status: str) -> None:
        super().__init__("organization_not_active", f"Organization status '{status}' does not permit this action")


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
