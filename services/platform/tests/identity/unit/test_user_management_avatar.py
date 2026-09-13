from __future__ import annotations

from io import BytesIO

import pytest
from app.identity.application.user_management import MAX_AVATAR_BYTES, UserManagementService
from app.identity.domain.entities import User
from app.identity.domain.exceptions import AvatarNotFoundError, InvalidAvatarError
from app.identity.domain.value_objects import Email
from app.identity.presentation.users_router import update_my_avatar
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.logging.audit_logger import AuditLogger
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.token import TokenClaims
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.platform_core.storage.interfaces import StoredFileRef
from fastapi import UploadFile

from tests.identity.unit.fakes import FakeAuditRecordSink, FakeUnitOfWork

pytestmark = pytest.mark.asyncio

_PNG = b"\x89PNG\r\n\x1a\ncontrolled-avatar-content"


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    async def put(self, *, key: str, content: bytes, content_type: str) -> StoredFileRef:
        self.objects[key] = (content, content_type)
        return StoredFileRef(key, len(content), content_type)

    async def get(self, *, key: str):
        yield self.objects[key][0]

    async def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)

    async def exists(self, *, key: str) -> bool:
        return key in self.objects

    async def generate_presigned_url(self, *, key: str, ttl_seconds: int) -> str:
        return f"https://storage.invalid/{key}"


def _service(uow: FakeUnitOfWork, storage: _MemoryStorage) -> UserManagementService:
    return UserManagementService(
        uow_factory=lambda: uow,
        password_hasher=PasswordHashingService(),
        dispatcher=EventDispatcher(),
        audit_logger=AuditLogger(FakeAuditRecordSink()),
        file_storage=storage,
    )


async def _user_in(uow: FakeUnitOfWork, org_id: OrgId, email: str) -> User:
    user = User.register(
        org_id=org_id,
        email=Email(email),
        password_hash="not-used",
        display_name="Avatar User",
    )
    await uow.users.add(user)
    return user


async def test_avatar_uses_the_resources_actual_org_and_can_be_retrieved() -> None:
    uow = FakeUnitOfWork()
    storage = _MemoryStorage()
    actual_org_id = OrgId(new_uuid7())
    user = await _user_in(uow, actual_org_id, "avatar@example.com")

    profile = await _service(uow, storage).update_avatar(
        user_id=user.id, content=_PNG, content_type="image/png"
    )

    assert profile.avatar_storage_key is not None
    assert profile.avatar_storage_key.startswith(f"avatars/{actual_org_id}/{user.id}/")
    assert profile.avatar_storage_key.endswith(".png")
    avatar = await _service(uow, storage).get_avatar(user_id=user.id)
    assert avatar.content_type == "image/png"
    assert b"".join([chunk async for chunk in avatar.chunks]) == _PNG


async def test_a_different_tenants_user_cannot_receive_another_users_avatar() -> None:
    uow = FakeUnitOfWork()
    storage = _MemoryStorage()
    user_a = await _user_in(uow, OrgId(new_uuid7()), "a@example.com")
    user_b = await _user_in(uow, OrgId(new_uuid7()), "b@example.com")
    await _service(uow, storage).update_avatar(
        user_id=user_a.id, content=_PNG, content_type="image/png"
    )

    with pytest.raises(AvatarNotFoundError):
        await _service(uow, storage).get_avatar(user_id=user_b.id)


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"", "image/png"),
        (b"not-an-image", "image/png"),
        (_PNG, "image/svg+xml"),
        (b"GIF89a-content", "image/jpeg"),
    ],
)
async def test_invalid_avatar_content_is_rejected_before_storage(
    content: bytes, content_type: str
) -> None:
    uow = FakeUnitOfWork()
    storage = _MemoryStorage()
    user = await _user_in(uow, OrgId(new_uuid7()), "invalid@example.com")

    with pytest.raises(InvalidAvatarError):
        await _service(uow, storage).update_avatar(
            user_id=user.id, content=content, content_type=content_type
        )

    assert storage.objects == {}


async def test_replacing_an_avatar_removes_the_previous_object() -> None:
    uow = FakeUnitOfWork()
    storage = _MemoryStorage()
    user = await _user_in(uow, OrgId(new_uuid7()), "replace@example.com")
    service = _service(uow, storage)
    first = await service.update_avatar(user_id=user.id, content=_PNG, content_type="image/png")
    second_content = _PNG + b"-changed"

    second = await service.update_avatar(
        user_id=user.id, content=second_content, content_type="image/png"
    )

    assert first.avatar_storage_key != second.avatar_storage_key
    assert first.avatar_storage_key in storage.deleted
    assert list(storage.objects) == [second.avatar_storage_key]


class _UnusedService:
    called = False

    async def update_avatar(self, **kwargs):
        self.called = True


async def test_http_upload_is_bounded_before_the_service_is_called() -> None:
    service = _UnusedService()
    user_id = new_uuid7()
    upload = UploadFile(
        filename="oversized.png",
        file=BytesIO(b"x" * (MAX_AVATAR_BYTES + 1)),
    )

    with pytest.raises(InvalidAvatarError):
        await update_my_avatar(
            file=upload,
            claims=TokenClaims(user_id, new_uuid7(), (), 0),
            service=service,  # type: ignore[arg-type]
        )

    assert service.called is False
