"""API Versioning: URL-path versioning (/api/v1/...), per ADR-established
convention. This helper builds a version-prefixed APIRouter so every
bounded context's router is mounted consistently."""

from __future__ import annotations

from fastapi import APIRouter


def versioned_router(*, version: str, tags: list[str]) -> APIRouter:
    return APIRouter(prefix=f"/api/{version}", tags=tags)
