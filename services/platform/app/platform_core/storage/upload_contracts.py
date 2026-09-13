"""Upload Contracts: the validated shape of an inbound upload request,
enforced before any bytes reach a FileStorageProvider."""

from __future__ import annotations

import json

from pydantic import BaseModel, field_validator

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
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

    @field_validator("filename")
    @classmethod
    def _filename_is_safe(cls, value: str) -> str:
        filename = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or len(filename) > 255:
            raise ValueError("Filename must contain between 1 and 255 characters")
        if any(ord(character) < 32 for character in filename):
            raise ValueError("Filename contains control characters")
        return filename

    @field_validator("content_type")
    @classmethod
    def _content_type_allowed(cls, value: str) -> str:
        if value not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Content type '{value}' is not permitted for upload")
        return value

    @field_validator("size_bytes")
    @classmethod
    def _size_within_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("File must not be empty")
        if value > MAX_UPLOAD_BYTES:
            raise ValueError(f"File exceeds the {MAX_UPLOAD_BYTES} byte upload limit")
        return value


def content_matches_declared_type(content: bytes, content_type: str) -> bool:
    """Small allow-list signature check before private object storage.

    This is not presented as malware scanning; it prevents obvious MIME
    spoofing and executable uploads while a dedicated scanner remains a
    separate deployment concern.
    """
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-")
    try:
        decoded = content.decode("utf-8")
        if content_type == "application/json":
            json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return content_type in {"text/plain", "text/csv", "application/json"}
