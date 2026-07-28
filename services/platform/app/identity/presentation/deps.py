"""
Shared FastAPI dependencies for the Identity presentation layer.

Every `get_*` function below is a placeholder resolved by composition.py
via `app.dependency_overrides` — routers depend on these functions, never
on a concrete service instance, so the presentation layer has no
construction-order dependency on composition.py.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.identity.application.authentication import AuthenticationService, OAuth2LoginService
from app.identity.application.email_verification import EmailVerificationService
from app.identity.application.mfa import MfaService
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.application.password_management import PasswordManagementService
from app.identity.application.rbac_engine import PermissionEvaluator
from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.application.security import AuditLogQueryService, SecurityService
from app.identity.application.team_management import TeamService
from app.identity.application.user_management import UserManagementService
from app.platform_core.errors.api_exceptions import UnauthorizedError
from app.platform_core.security.token import JwtTokenService, TokenClaims

# auto_error=False: a missing/malformed Authorization header must still
# raise *our* UnauthorizedError (same shape/message every other auth
# failure in this codebase uses), not HTTPBearer's own default
# HTTPException(403, "Not authenticated"). Being a fastapi.security.SecurityBase
# instance is what makes FastAPI register this as an OpenAPI security
# scheme and show Swagger's global "Authorize" button — that registration
# happens because of the type of this object, not because of how routers
# depend on it, so every existing router keeps working unchanged via
# Depends(get_current_user_claims).
_bearer_scheme = HTTPBearer(auto_error=False)


def get_token_service() -> JwtTokenService:
    raise NotImplementedError("JwtTokenService dependency not wired")


def get_authentication_service() -> AuthenticationService:
    raise NotImplementedError("AuthenticationService dependency not wired")


def get_oauth2_login_service() -> OAuth2LoginService:
    raise NotImplementedError("OAuth2LoginService dependency not wired")


def get_user_management_service() -> UserManagementService:
    raise NotImplementedError("UserManagementService dependency not wired")


def get_email_verification_service() -> EmailVerificationService:
    raise NotImplementedError("EmailVerificationService dependency not wired")


def get_password_management_service() -> PasswordManagementService:
    raise NotImplementedError("PasswordManagementService dependency not wired")


def get_mfa_service() -> MfaService:
    raise NotImplementedError("MfaService dependency not wired")


def get_organization_management_service() -> OrganizationManagementService:
    raise NotImplementedError("OrganizationManagementService dependency not wired")


def get_team_service() -> TeamService:
    raise NotImplementedError("TeamService dependency not wired")


def get_role_service() -> RoleService:
    raise NotImplementedError("RoleService dependency not wired")


def get_permission_catalog_service() -> PermissionCatalogService:
    raise NotImplementedError("PermissionCatalogService dependency not wired")


def get_permission_evaluator() -> PermissionEvaluator:
    raise NotImplementedError("PermissionEvaluator dependency not wired")


def get_security_service() -> SecurityService:
    raise NotImplementedError("SecurityService dependency not wired")


def get_audit_log_query_service() -> AuditLogQueryService:
    raise NotImplementedError("AuditLogQueryService dependency not wired")


async def get_current_user_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    token_service: JwtTokenService = Depends(get_token_service),
) -> TokenClaims:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing or malformed Authorization header")
    try:
        return token_service.verify(credentials.credentials)
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc
