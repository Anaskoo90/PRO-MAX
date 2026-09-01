"""Application-layer DTOs shared across Identity command/query handlers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.identity.domain.entities import User


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int = 900


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Either `tokens` is set (login complete) or `mfa_challenge_user_id`
    is set (caller must call VerifyMfaChallenge next) — never both."""

    tokens: AuthTokens | None = None
    mfa_challenge_user_id: UUID | None = None
    mfa_available_factors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UserProfileDTO:
    id: UUID
    org_id: UUID
    email: str
    display_name: str
    status: str
    mfa_enabled: bool
    avatar_storage_key: str | None
    preferences: dict[str, Any]


def user_to_profile_dto(user: User) -> UserProfileDTO:
    """Shared User -> UserProfileDTO mapping — used by both
    UserManagementService (self-service profile endpoints) and
    OrganizationManagementService (admin member listing/detail), so an
    org admin's view of a member is built the same way a user's view of
    their own profile is, not a second ad-hoc mapping."""
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


@dataclass(frozen=True, slots=True)
class SessionDTO:
    id: UUID
    device_label: str
    ip_address: str
    created_at: datetime
    expires_at: datetime
    is_current: bool
