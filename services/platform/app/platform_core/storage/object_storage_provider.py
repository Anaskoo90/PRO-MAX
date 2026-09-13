"""
Object Storage Provider: S3-compatible implementation (works against AWS
S3, MinIO, or any S3-API-compatible provider — the cloud provider itself is
still undecided per the standing gap, but the S3 API is the de facto
portable interface regardless of which provider is eventually chosen).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from app.platform_core.errors.infrastructure_exceptions import StorageError
from app.platform_core.storage.interfaces import StoredFileRef


class S3CompatibleStorageProvider:
    def __init__(
        self,
        *,
        bucket: str,
        client: Any | None = None,
        client_factory: Any | None = None,
    ) -> None:
        """Accept either an active client (tests) or an aioboto3 client factory.

        The factory form opens and closes a client per operation, avoiding an
        unclosed async context when the provider is constructed synchronously.
        """
        if (client is None) == (client_factory is None):
            raise ValueError("Provide exactly one of client or client_factory")
        self._client = client
        self._client_factory = client_factory
        self._bucket = bucket

    @asynccontextmanager
    async def _open_client(self):
        if self._client is not None:
            yield self._client
            return
        async with self._client_factory() as client:
            yield client

    async def put(self, *, key: str, content: bytes, content_type: str) -> StoredFileRef:
        try:
            async with self._open_client() as client:
                await client.put_object(
                    Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
                )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError(f"Failed to store object '{key}'") from exc
        return StoredFileRef(storage_key=key, size_bytes=len(content), content_type=content_type)

    async def get(self, *, key: str) -> AsyncIterator[bytes]:
        try:
            async with self._open_client() as client:
                response = await client.get_object(Bucket=self._bucket, Key=key)
                async for chunk in response["Body"].iter_chunks():
                    yield chunk
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError(f"Failed to read object '{key}'") from exc

    async def delete(self, *, key: str) -> None:
        try:
            async with self._open_client() as client:
                await client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError(f"Failed to delete object '{key}'") from exc

    async def exists(self, *, key: str) -> bool:
        try:
            async with self._open_client() as client:
                await client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise StorageError(f"Failed to inspect object '{key}'") from exc
        except (BotoCoreError, OSError) as exc:
            raise StorageError(f"Failed to inspect object '{key}'") from exc

    async def generate_presigned_url(self, *, key: str, ttl_seconds: int) -> str:
        try:
            async with self._open_client() as client:
                return await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=ttl_seconds,
                )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError(f"Failed to sign object '{key}'") from exc
