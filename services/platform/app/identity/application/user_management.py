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

from typing import Any

from app.identity.application.dtos import UserProfileDTO
from app.identity.domain.entities import PasswordHistoryEntry, User
from app.identity.domain.exceptions import (
    EmailAlreadyRegisteredError,
    UserNotFoundError,
    WeakPasswordError,
)
from app.identity.domain.value_objects import Email
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY, PasswordPolicy
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.storage.interfaces import FileStorageProvider
from app.platform_core.storage.upload_contracts import UploadRequest


def _to_profile_dto(user: User) -> UserProfileDTO:
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
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            await self._audit_logger.record(
                org_id=org_id, actor_id=user.id, action="user_registered", resource_type="user", resource_id=str(user.id)
            )
            return _to_profile_dto(user)

    async def get_profile(self, *, user_id: EntityId) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            return _to_profile_dto(user)

    async def update_profile(self, *, user_id: EntityId, display_name: str | None) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.update_profile(display_name=display_name)
            await uow.users.update(user)
            await uow.commit()
            return _to_profile_dto(user)

    async def update_avatar(self, *, user_id: EntityId, content: bytes, content_type: str, filename: str) -> UserProfileDTO:
        UploadRequest(filename=filename, content_type=content_type, size_bytes=len(content))  # raises on invalid upload

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)

            storage_key = f"avatars/{user.org_id}/{user.id}/{filename}"
            await self._file_storage.put(key=storage_key, content=content, content_type=content_type)
            user.update_avatar(storage_key)
            await uow.users.update(user)
            await uow.commit()
            return _to_profile_dto(user)

    async def update_preferences(self, *, user_id: EntityId, preferences: dict[str, Any]) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.update_preferences(preferences)
            await uow.users.update(user)
            await uow.commit()
            return _to_profile_dto(user)

    async def suspend(self, *, user_id: EntityId, reason: str) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.suspend(reason=reason)
            await uow.users.update(user)
            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            await self._audit_logger.record(
                org_id=user.org_id, actor_id=None, action="user_suspended", resource_type="user",
                resource_id=str(user.id), metadata={"reason": reason},
            )
            return _to_profile_dto(user)

    async def reactivate(self, *, user_id: EntityId) -> UserProfileDTO:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            user.reactivate()
            await uow.users.update(user)
            events = user.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_profile_dto(user)

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
            user.deactivate()
            await uow.users.update(user)
            await uow.commit()
