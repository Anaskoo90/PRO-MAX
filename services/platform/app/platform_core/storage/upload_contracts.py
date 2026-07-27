"""Upload Contracts: the validated shape of an inbound upload request,
enforced before any bytes reach a FileStorageProvider."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
_ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/json",
}


class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int

    @field_validator("content_type")
    @classmethod
    def _content_type_allowed(cls, value: str) -> str:
        if value not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Content type '{value}' is not permitted for upload")
        return value

    @field_validator("size_bytes")
    @classmethod
    def _size_within_limit(cls, value: int) -> int:
        if value > _DEFAULT_MAX_UPLOAD_BYTES:
            raise ValueError(f"File exceeds the {_DEFAULT_MAX_UPLOAD_BYTES} byte upload limit")
        return value
