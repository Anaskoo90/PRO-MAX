"""
Object Storage Provider: S3-compatible implementation (works against AWS
S3, MinIO, or any S3-API-compatible provider — the cloud provider itself is
still undecided per the standing gap, but the S3 API is the de facto
portable interface regardless of which provider is eventually chosen).
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.platform_core.storage.interfaces import StoredFileRef


class S3CompatibleStorageProvider:
    def __init__(self, *, client: Any, bucket: str) -> None:
        """`client` is an aioboto3 S3 client, injected rather than
        constructed here, so tests can pass a stub without a real
        connection."""
        self._client = client
        self._bucket = bucket

    async def put(self, *, key: str, content: bytes, content_type: str) -> StoredFileRef:
        await self._client.put_object(
            Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
        )
        return StoredFileRef(storage_key=key, size_bytes=len(content), content_type=content_type)

    async def get(self, *, key: str) -> AsyncIterator[bytes]:
        response = await self._client.get_object(Bucket=self._bucket, Key=key)
        async for chunk in response["Body"].iter_chunks():
            yield chunk

    async def delete(self, *, key: str) -> None:
        await self._client.delete_object(Bucket=self._bucket, Key=key)

    async def exists(self, *, key: str) -> bool:
        try:
            await self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.ClientError:
            return False

    async def generate_presigned_url(self, *, key: str, ttl_seconds: int) -> str:
        return await self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
