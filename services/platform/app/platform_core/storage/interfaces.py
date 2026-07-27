"""Storage Interfaces: the Protocol every File Service provider (local disk
for dev, object storage for staging/prod) implements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass(frozen=True, slots=True)
class StoredFileRef:
    storage_key: str
    size_bytes: int
    content_type: str


class FileStorageProvider(Protocol):
    async def put(
        self, *, key: str, content: bytes, content_type: str
    ) -> StoredFileRef: ...

    async def get(self, *, key: str) -> AsyncIterator[bytes]: ...

    async def delete(self, *, key: str) -> None: ...

    async def exists(self, *, key: str) -> bool: ...

    async def generate_presigned_url(self, *, key: str, ttl_seconds: int) -> str: ...
