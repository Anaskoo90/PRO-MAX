"""
User Management submodule: registration, profile, avatar, preferences,
status, lifecycle.

Registration deliberately does not call EmailVerificationService directly —
it dispatches UserRegistered (already recorded by User.register()) and
EmailVerificationService subscribes to it in composition.py. This keeps the
two submodules decoupled at the same in-process EventDispatcher seam the
rest of the platform uses ("publishers never know subscribers", ADR-006),
rather than one submodule importing the other.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.identity.application.dtos import UserProfileDTO, user_to_profile_dto
from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.identity.domain.entities import PasswordHistoryEntry, User
from app.identity.domain.exceptions import (
    AvatarNotFoundError,
    EmailAlreadyRegisteredError,
    InvalidAvatarError,
    OrganizationOwnerProtectedError,
    UserNotFoundError,
    WeakPasswordError,
)
from app.identity.domain.value_objects import Email
from app.platform_core.errors.infrastructure_exceptions import StorageError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.events.integration_event import append_domain_events_to_outbox
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.logging.logger import get_logger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY, PasswordPolicy
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.storage.interfaces import FileStorageProvider

MAX_AVATAR_BYTES = 5 * 1024 * 1024
_AVATAR_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
}
_logger = get_logger("identity.user_management")


@dataclass(frozen=True, slots=True)
class AvatarContent:
    chunks: AsyncIterator[bytes]
    content_type: str


def _validate_avatar(content: bytes, content_type: str) -> str:
    normalized_type = content_type.lower().strip()
    if normalized_type not in _AVATAR_EXTENSIONS:
        raise InvalidAvatarError("Avatar must be a PNG, JPEG, or GIF image")
    if not content:
        raise InvalidAvatarError("Avatar must not be empty")
    if len(content) > MAX_AVATAR_BYTES:
        raise InvalidAvatarError(f"Avatar exceeds the {MAX_AVATAR_BYTES} byte upload limit")

    signature_is_valid = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9"),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
    }[normalized_type]
    if not signature_is_valid:
        raise InvalidAvatarError("Avatar bytes do not match the declared image type")
    return normalized_type


def _avatar_content_type(storage_key: str) -> str:
    extension = storage_key.rsplit(".", maxsplit=1)[-1].lower()
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
    }.get(extension, "application/octet-stream")


class UserManagementService:
    def __init__(
        self,
        *,
        uow_factory,
        password_hasher: PasswordHashingService,
        dispatcher: EventDispatcher,
        audit_logger: AuditLogger,
        file_storage: FileStorageProvider,
        password_policy: PasswordPolicy = DEFAULT_PASSWORD_POLICY,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._dispatcher = dispatcher
        self._audit_logger = audit_logger
        self._file_storage = file_storage
        self._password_policy = password_policy

    async def register(
        self, *, org_id: OrgId, email: str, password: str, display_name: str
    ) -> UserProfileDTO:
        violations = self._password_policy.violations(password)
        if violations:
            raise WeakPasswordError(violations)

        email_vo = Email(email)
        async with self._uow_factory() as uow:
            existing = await uow.users.get_by_email(org_id, email_vo.value)
            if existing is not None:
                raise EmailAlreadyRegisteredError(email_vo.value)

            password_hash = self._password_hasher.hash(password)
            user = User.register(
                org_id=org_id, email=email_vo, password_hash=password_hash, display_name=display_name
            )
            await uow.users.add(user)
            # Flush before adding the password-history row: password_history
            # has a real FK on users.id, but the two ORM models have no
            # relationship() between them (by design — see orm_models.py),
            # so SQLAlchemy won't auto-order the two INSERTs across a single
            # flush. Without this, the password_history insert can be sent
            # before the user row exists, violating the FK constraint.
            await uow.flush()
            await uow.password_history.add(
                PasswordHistoryEntry.create(user_id=user.id, password_hash=password_hash)
            )
            events = user.pull_domain_events()
            await append_domain_events_to_outbox(
                uow.outbox,
                events,
                org_id=user.org_id,
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            await self._audit_logger.record(
                org_id=org_id, actor_id=user.id, action="user_registered", resource_type="user", resource_id=str(user.id)
            )
            return user_to_profile_dto(user)

    async def get_profile(self, *, user_id: EntityId) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            return user_to_profile_dto(user)

    async def update_profile(self, *, user_id: EntityId, display_name: str | None) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.update_profile(display_name=display_name)
            await uow.users.update(user)
            await uow.commit()
            return user_to_profile_dto(user)

    async def update_avatar(
        self, *, user_id: EntityId, content: bytes, content_type: str
    ) -> UserProfileDTO:
        normalized_type = _validate_avatar(content, content_type)

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)

            extension = _AVATAR_EXTENSIONS[normalized_type]
            digest = sha256(content).hexdigest()
            storage_key = f"avatars/{user.org_id}/{user.id}/{digest}.{extension}"
            previous_storage_key = user.avatar_storage_key
            await self._file_storage.put(
                key=storage_key, content=content, content_type=normalized_type
            )
            user.update_avatar(storage_key)
            try:
                await uow.users.update(user)
                await uow.commit()
            except Exception:
                try:
                    await self._file_storage.delete(key=storage_key)
                except StorageError:
                    await _logger.aerror(
                        "avatar_rollback_cleanup_failed",
                        storage_key=storage_key,
                        exc_info=True,
                    )
                raise

            if previous_storage_key and previous_storage_key != storage_key:
                try:
                    await self._file_storage.delete(key=previous_storage_key)
                except StorageError:
                    # The database already points at the new immutable object;
                    # failed garbage collection must not turn a successful
                    # update into a misleading client-visible failure.
                    await _logger.aerror(
                        "previous_avatar_cleanup_failed",
                        storage_key=previous_storage_key,
                        exc_info=True,
                    )
            await self._audit_logger.record(
                org_id=user.org_id,
                actor_id=user.id,
                action="user_avatar_updated",
                resource_type="user",
                resource_id=str(user.id),
            )
            return user_to_profile_dto(user)

    async def get_avatar(self, *, user_id: EntityId) -> AvatarContent:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            storage_key = user.avatar_storage_key

        if not storage_key or not await self._file_storage.exists(key=storage_key):
            raise AvatarNotFoundError(user_id)
        return AvatarContent(
            chunks=self._file_storage.get(key=storage_key),
            content_type=_avatar_content_type(storage_key),
        )

    async def update_preferences(self, *, user_id: EntityId, preferences: dict[str, Any]) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.update_preferences(preferences)
            await uow.users.update(user)
            await uow.commit()
            return user_to_profile_dto(user)

    async def suspend(
        self,
        *,
        org_id: OrgId,
        user_id: EntityId,
        reason: str,
        actor_user_id: UserId,
    ) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            # Organization row first (same lock order as ownership transfer):
            # otherwise a transfer to this very user could commit between our
            # "is this the owner?" check and our write, leaving the freshly
            # designated owner suspended.
            org = await uow.organizations.get_by_id_for_update(org_id)
            user = await uow.users.get_by_id(user_id)
            if user is None or user.org_id != org_id:
                raise UserNotFoundError(user_id)
            self._assert_not_organization_owner(org, user, action="suspend")
            user.suspend(reason=reason)
            await uow.users.update(user)
            await self._revoke_all_sessions(uow, user)
            events = user.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=user.org_id,
                    category=AuditEventCategory.USER_CHANGE,
                    action="user_suspended",
                    actor_user_id=actor_user_id,
                    resource_type="user",
                    resource_id=str(user.id),
                    metadata={"reason": reason},
                )
            )
            await append_domain_events_to_outbox(
                uow.outbox,
                events,
                org_id=user.org_id,
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            await self._audit_logger.record(
                org_id=user.org_id, actor_id=actor_user_id, action="user_suspended", resource_type="user",
                resource_id=str(user.id), metadata={"reason": reason},
            )
            return user_to_profile_dto(user)

    async def reactivate(
        self,
        *,
        org_id: OrgId,
        user_id: EntityId,
        actor_user_id: UserId,
    ) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None or user.org_id != org_id:
                raise UserNotFoundError(user_id)
            user.reactivate()
            await uow.users.update(user)
            events = user.pull_domain_events()
            await uow.audit_logs.add(
                AuditLogRecord.create(
                    org_id=user.org_id,
                    category=AuditEventCategory.USER_CHANGE,
                    action="user_reactivated",
                    actor_user_id=actor_user_id,
                    resource_type="user",
                    resource_id=str(user.id),
                )
            )
            await append_domain_events_to_outbox(
                uow.outbox,
                events,
                org_id=user.org_id,
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return user_to_profile_dto(user)

    async def deactivate_account(self, *, user_id: EntityId) -> None:
        """User-initiated account closure: status -> deactivated. Distinct
        from an admin-initiated hard delete (out of scope here — no
        requirement to permanently erase identity records was specified,
        and soft-delete via `deleted_at` is the platform-wide default for
        entity tables regardless)."""
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            # The plain read above only supplies org_id (immutable); the
            # organization row is locked before anything is written, and the
            # owner check runs against the locked, current row.
            org = await uow.organizations.get_by_id_for_update(user.org_id)
            self._assert_not_organization_owner(org, user, action="deactivate")
            user.deactivate()
            await uow.users.update(user)
            await self._revoke_all_sessions(uow, user)
            await uow.commit()

    @staticmethod
    async def _revoke_all_sessions(uow, user: User) -> None:
        """Same pattern password reset uses: a status change that bars the
        account from authenticating must also kill every session it already
        holds, otherwise outstanding refresh tokens keep working."""
        for session in await uow.sessions.list_active_for_user(user.id):
            session.revoke()
            await uow.sessions.update(session)

    @staticmethod
    def _assert_not_organization_owner(org, user: User, *, action: str) -> None:
        """The designated owner can only be removed from play after an
        ownership transfer (OrganizationManagementService.transfer_ownership).
        `org` must be the row loaded with get_by_id_for_update."""
        if org is not None and org.owner_user_id == user.id:
            raise OrganizationOwnerProtectedError(action)
