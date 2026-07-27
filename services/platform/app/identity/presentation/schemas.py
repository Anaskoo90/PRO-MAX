"""Request/response schemas for the Identity API. Kept separate from
application-layer DTOs (app.identity.application.dtos) so the wire contract
can evolve independently of the internal DTO shape."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterUserRequest(BaseModel):
    org_id: UUID
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    org_id: UUID
    email: EmailStr
    password: str
    remember_me: bool = False


class MfaChallengeResponse(BaseModel):
    mfa_required: bool = True
    mfa_challenge_user_id: UUID
    available_factors: list[str]


class VerifyMfaChallengeRequest(BaseModel):
    user_id: UUID
    code: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class UserProfileResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    display_name: str
    status: str
    mfa_enabled: bool
    avatar_storage_key: str | None
    preferences: dict[str, Any]


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)


class UpdatePreferencesRequest(BaseModel):
    preferences: dict[str, Any]


class SessionResponse(BaseModel):
    id: UUID
    device_label: str
    ip_address: str
    created_at: datetime
    expires_at: datetime
    is_current: bool


class SendVerificationRequest(BaseModel):
    pass


class VerifyEmailRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=128)


class RequestPasswordResetRequest(BaseModel):
    org_id: UUID
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=1, max_length=128)


class TotpEnrollmentResponse(BaseModel):
    factor_id: UUID
    secret: str
    provisioning_uri: str


class ConfirmTotpEnrollmentRequest(BaseModel):
    factor_id: UUID
    code: str


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class OAuth2AuthorizationUrlResponse(BaseModel):
    authorization_url: str
    state: str


class OAuth2CallbackRequest(BaseModel):
    org_id: UUID
    code: str


# --- Organization ---------------------------------------------------------


class RegisterOrganizationRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=50)
    owner_email: EmailStr
    owner_password: str = Field(min_length=1, max_length=128)
    owner_display_name: str = Field(min_length=1, max_length=200)


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    owner_user_id: UUID
    status: str
    settings: dict[str, Any]


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class UpdateOrganizationSettingsRequest(BaseModel):
    settings: dict[str, Any]


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: UUID


# --- Teams ------------------------------------------------------------------


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    parent_team_id: UUID | None = None


class UpdateTeamRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class SetTeamParentRequest(BaseModel):
    parent_team_id: UUID | None = None


class TeamResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: str
    parent_team_id: UUID | None


class AddTeamMemberRequest(BaseModel):
    user_id: UUID
    team_role: str = "member"


class UpdateTeamMemberRoleRequest(BaseModel):
    team_role: str


class TeamMembershipResponse(BaseModel):
    id: UUID
    team_id: UUID
    user_id: UUID
    team_role: str


# --- Roles & Permissions -----------------------------------------------------


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""


class UpdateRoleRequest(BaseModel):
    name: str | None = None


class SetRoleParentRequest(BaseModel):
    parent_role_id: UUID | None = None


class RoleResponse(BaseModel):
    id: UUID
    org_id: UUID | None
    name: str
    description: str
    is_system_role: bool
    parent_role_id: UUID | None
    permission_ids: list[UUID]


class GrantPermissionRequest(BaseModel):
    permission_id: UUID


class AssignRoleRequest(BaseModel):
    user_id: UUID
    role_id: UUID


class PermissionResponse(BaseModel):
    id: UUID
    resource: str
    action: str
    description: str


# --- Security -----------------------------------------------------------


class TrustDeviceRequest(BaseModel):
    label: str = ""


class TrustedDeviceResponse(BaseModel):
    id: UUID
    label: str
    trusted_until: datetime


class AuditLogResponse(BaseModel):
    id: UUID
    org_id: UUID
    category: str
    action: str
    actor_user_id: UUID | None
    resource_type: str
    resource_id: str
    ip_address: str | None
    metadata: dict[str, Any]
    occurred_at: datetime
