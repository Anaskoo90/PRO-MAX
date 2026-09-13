from __future__ import annotations

import pytest
from app.platform_core.errors.infrastructure_exceptions import StorageError
from app.platform_core.storage.local_provider import LocalFileStorageProvider
from app.platform_core.storage.object_storage_provider import S3CompatibleStorageProvider
from botocore.exceptions import ClientError

pytestmark = pytest.mark.asyncio


class _Body:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def iter_chunks(self):
        yield self._content[:2]
        yield self._content[2:]


class _S3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, **kwargs) -> None:
        self.objects[kwargs["Key"]] = kwargs["Body"]

    async def get_object(self, **kwargs):
        return {"Body": _Body(self.objects[kwargs["Key"]])}

    async def delete_object(self, **kwargs) -> None:
        self.objects.pop(kwargs["Key"], None)

    async def head_object(self, **kwargs) -> None:
        if kwargs["Key"] not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "missing"}}, "HeadObject"
            )

    async def generate_presigned_url(self, operation, **kwargs) -> str:
        return f"https://storage.invalid/{kwargs['Params']['Key']}"


async def test_local_storage_round_trip_and_traversal_protection(tmp_path) -> None:
    provider = LocalFileStorageProvider(tmp_path)
    await provider.put(key="avatars/user/image.png", content=b"image", content_type="image/png")

    assert await provider.exists(key="avatars/user/image.png") is True
    assert b"".join([chunk async for chunk in provider.get(key="avatars/user/image.png")]) == b"image"
    with pytest.raises(ValueError, match="escapes the storage root"):
        await provider.put(key="../outside", content=b"bad", content_type="text/plain")

    await provider.delete(key="avatars/user/image.png")
    assert await provider.exists(key="avatars/user/image.png") is False


async def test_s3_compatible_storage_round_trip() -> None:
    client = _S3Client()
    provider = S3CompatibleStorageProvider(bucket="guilddesk", client=client)

    stored = await provider.put(key="avatar.png", content=b"image", content_type="image/png")

    assert stored.size_bytes == 5
    assert await provider.exists(key="avatar.png") is True
    assert b"".join([chunk async for chunk in provider.get(key="avatar.png")]) == b"image"
    assert await provider.generate_presigned_url(key="avatar.png", ttl_seconds=60) == (
        "https://storage.invalid/avatar.png"
    )
    await provider.delete(key="avatar.png")
    assert await provider.exists(key="avatar.png") is False


async def test_s3_provider_maps_non_not_found_client_errors() -> None:
    class _ForbiddenClient(_S3Client):
        async def head_object(self, **kwargs) -> None:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "HeadObject"
            )

    provider = S3CompatibleStorageProvider(bucket="guilddesk", client=_ForbiddenClient())

    with pytest.raises(StorageError, match="inspect object"):
        await provider.exists(key="avatar.png")


async def test_s3_provider_requires_exactly_one_client_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        S3CompatibleStorageProvider(bucket="guilddesk")
    with pytest.raises(ValueError, match="exactly one"):
        S3CompatibleStorageProvider(bucket="guilddesk", client=object(), client_factory=object())
