"""Local Provider: filesystem-backed FileStorageProvider, for local dev
and CI only — never selected when EnvironmentProfile.is_production_like."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles

from app.platform_core.errors.infrastructure_exceptions import StorageError
from app.platform_core.storage.interfaces import StoredFileRef


class LocalFileStorageProvider:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        resolved = (self._root_dir / key).resolve()
        if self._root_dir.resolve() not in resolved.parents and resolved != self._root_dir.resolve():
            raise ValueError(f"Storage key '{key}' escapes the storage root")
        return resolved

    async def put(self, *, key: str, content: bytes, content_type: str) -> StoredFileRef:
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, "wb") as f:
                await f.write(content)
        except OSError as exc:
            raise StorageError(f"Failed to store local object '{key}'") from exc
        return StoredFileRef(storage_key=key, size_bytes=len(content), content_type=content_type)

    async def get(self, *, key: str) -> AsyncIterator[bytes]:
        path = self._resolve(key)
        try:
            async with aiofiles.open(path, "rb") as f:
                while chunk := await f.read(65536):
                    yield chunk
        except OSError as exc:
            raise StorageError(f"Failed to read local object '{key}'") from exc

    async def delete(self, *, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"Failed to delete local object '{key}'") from exc

    async def exists(self, *, key: str) -> bool:
        try:
            return self._resolve(key).exists()
        except OSError as exc:
            raise StorageError(f"Failed to inspect local object '{key}'") from exc

    async def generate_presigned_url(self, *, key: str, ttl_seconds: int) -> str:
        raise NotImplementedError(
            "LocalFileStorageProvider has no HTTP surface to presign — "
            "use ObjectStorageProvider outside local dev"
        )
