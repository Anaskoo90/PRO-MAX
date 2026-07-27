"""
Identity domain entities.

Plain Python classes, not pydantic models and not SQLAlchemy models — the
domain layer depends on nothing outside shared_kernel/events (ADR-005..009's
dependency rule). Infrastructure repositories translate to/from these and
the ORM models in infrastructure/orm_models.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.identity.domain.events import (
    MfaDisabled,
    MfaEnabled,
    PasswordChanged,
    UserEmailVerified,
    UserRegistered,
    UserReactivated,
    UserSuspended,
)
from app.identity.domain.exceptions import AccountNotActiveError, EmailAlreadyVerifiedError
from app.identity.domain.value_objects import Email
from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class UserStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class MfaFactorType(StrEnum):
    TOTP = "totp"
    RECOVERY_CODE = "recovery_code"


class User(EventRecordingMixin):
    """Aggregate root. Owns MFA enrollment/verification decisions and
    password-change invariants; sessions are a separate aggregate (a user
    can have many concurrent sessions, and revoking one shouldn't require
    loading the whole session list through the User aggregate)."""

    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        email: Email,
        password_hash: str,
        status: UserStatus,
        display_name: str,
        mfa_enabled: bool = False,
        failed_login_attempts: int = 0,
        locked_until: datetime | None = None,
        preferences: dict[str, Any] | None = None,
        avatar_storage_key: str | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.email = email
        self.password_hash = password_hash
        self.status = status
        self.display_name = display_name
        self.mfa_enabled = mfa_enabled
        self.failed_login_attempts = failed_login_attempts
        self.locked_until = locked_until
        self.preferences = preferences or {}
        self.avatar_storage_key = avatar_storage_key
        self.version = version

    @classmethod
    def register(
        cls, *, org_id: OrgId, email: Email, password_hash: str, display_name: str
    ) -> "User":
        user = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            email=email,
            password_hash=password_hash,
            status=UserStatus.PENDING_VERIFICATION,
            display_name=display_name,
        )
        user.record_event(
            UserRegistered(aggregate_id=user.id, org_id=org_id, email=str(email))
        )
        return user

    def verify_email(self) -> None:
        if self.status != UserStatus.PENDING_VERIFICATION:
            raise EmailAlreadyVerifiedError()
        self.status = UserStatus.ACTIVE
        self.record_event(UserEmailVerified(aggregate_id=self.id, email=str(self.email)))

    def assert_can_authenticate(self) -> None:
        if self.status != UserStatus.ACTIVE:
            raise AccountNotActiveError(self.status.value)

    def record_failed_login(self, *, lockout_threshold: int, lockout_duration: timedelta) -> None:
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= lockout_threshold:
            self.locked_until = utcnow() + lockout_duration

    def record_successful_login(self) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None

    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()

    def change_password(self, new_password_hash: str) -> None:
        self.password_hash = new_password_hash
        self.record_event(PasswordChanged(aggregate_id=self.id))

    def suspend(self, *, reason: str) -> None:
        self.status = UserStatus.SUSPENDED
        self.record_event(UserSuspended(aggregate_id=self.id, reason=reason))

    def reactivate(self) -> None:
        self.status = UserStatus.ACTIVE
        self.record_event(UserReactivated(aggregate_id=self.id))

    def deactivate(self) -> None:
        self.status = UserStatus.DEACTIVATED

    def update_profile(self, *, display_name: str | None = None) -> None:
        if display_name is not None:
            self.display_name = display_name

    def update_avatar(self, storage_key: str) -> None:
        self.avatar_storage_key = storage_key

    def update_preferences(self, preferences: dict[str, Any]) -> None:
        self.preferences = {**self.preferences, **preferences}

    def mark_mfa_enabled(self, factor_type: MfaFactorType) -> None:
        self.mfa_enabled = True
        self.record_event(MfaEnabled(aggregate_id=self.id, factor_type=factor_type.value))

    def mark_mfa_disabled(self, factor_type: MfaFactorType) -> None:
        self.mfa_enabled = False
        self.record_event(MfaDisabled(aggregate_id=self.id, factor_type=factor_type.value))


class Session:
    """Separate aggregate root — see User's docstring for why."""

    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        refresh_token_hash: str,
        device_info: dict[str, Any] | None,
        ip_address: str,
        remember_me: bool,
        created_at: datetime,
        expires_at: datetime,
        revoked_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.refresh_token_hash = refresh_token_hash
        self.device_info = device_info or {}
        self.ip_address = ip_address
        self.remember_me = remember_me
        self.created_at = created_at
        self.expires_at = expires_at
        self.revoked_at = revoked_at

    @classmethod
    def create(
        cls,
        *,
        user_id: EntityId,
        refresh_token_hash: str,
        device_info: dict[str, Any] | None,
        ip_address: str,
        remember_me: bool,
    ) -> "Session":
        now = utcnow()
        ttl = timedelta(days=30) if remember_me else timedelta(hours=12)
        return cls(
            id=EntityId(new_uuid7()),
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            device_info=device_info,
            ip_address=ip_address,
            remember_me=remember_me,
            created_at=now,
            expires_at=now + ttl,
        )

    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > utcnow()

    def revoke(self) -> None:
        self.revoked_at = utcnow()

    def device_label(self) -> str:
        return str(self.device_info.get("label") or self.device_info.get("user_agent") or "Unknown device")


class MfaFactor:
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        factor_type: MfaFactorType,
        secret_encrypted: str | None,
        recovery_code_hash: str | None = None,
        verified_at: datetime | None = None,
        consumed_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.factor_type = factor_type
        self.secret_encrypted = secret_encrypted
        self.recovery_code_hash = recovery_code_hash
        self.verified_at = verified_at
        self.consumed_at = consumed_at
        self.created_at = created_at or utcnow()

    @classmethod
    def new_totp(cls, *, user_id: EntityId, secret_encrypted: str) -> "MfaFactor":
        return cls(
            id=EntityId(new_uuid7()),
            user_id=user_id,
            factor_type=MfaFactorType.TOTP,
            secret_encrypted=secret_encrypted,
        )

    @classmethod
    def new_recovery_code(cls, *, user_id: EntityId, recovery_code_hash: str) -> "MfaFactor":
        return cls(
            id=EntityId(new_uuid7()),
            user_id=user_id,
            factor_type=MfaFactorType.RECOVERY_CODE,
            secret_encrypted=None,
            recovery_code_hash=recovery_code_hash,
        )

    def mark_verified(self) -> None:
        self.verified_at = utcnow()

    def is_verified(self) -> bool:
        return self.verified_at is not None

    def mark_consumed(self) -> None:
        self.consumed_at = utcnow()

    def is_consumed(self) -> bool:
        return self.consumed_at is not None


class EmailVerificationToken:
    def __init__(
        self, *, id: EntityId, user_id: EntityId, token_hash: str, expires_at: datetime, consumed_at: datetime | None = None
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.consumed_at = consumed_at

    @classmethod
    def create(cls, *, user_id: EntityId, token_hash: str, ttl: timedelta = timedelta(hours=24)) -> "EmailVerificationToken":
        return cls(id=EntityId(new_uuid7()), user_id=user_id, token_hash=token_hash, expires_at=utcnow() + ttl)

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at

    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def consume(self) -> None:
        self.consumed_at = utcnow()


class PasswordResetToken:
    def __init__(
        self, *, id: EntityId, user_id: EntityId, token_hash: str, expires_at: datetime, consumed_at: datetime | None = None
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.consumed_at = consumed_at

    @classmethod
    def create(cls, *, user_id: EntityId, token_hash: str, ttl: timedelta = timedelta(hours=1)) -> "PasswordResetToken":
        return cls(id=EntityId(new_uuid7()), user_id=user_id, token_hash=token_hash, expires_at=utcnow() + ttl)

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at

    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def consume(self) -> None:
        self.consumed_at = utcnow()


class PasswordHistoryEntry:
    """Append-only — never deleted, per the platform-wide retention
    convention for historical records (Physical Schema's shared conventions)."""

    def __init__(self, *, id: EntityId, user_id: EntityId, password_hash: str, created_at: datetime | None = None) -> None:
        self.id = id
        self.user_id = user_id
        self.password_hash = password_hash
        self.created_at = created_at or utcnow()

    @classmethod
    def create(cls, *, user_id: EntityId, password_hash: str) -> "PasswordHistoryEntry":
        return cls(id=EntityId(new_uuid7()), user_id=user_id, password_hash=password_hash)
