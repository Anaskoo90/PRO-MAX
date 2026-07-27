"""
Platform-wide error code registry.

One flat enum, not per-context enums, so an error code is globally unique
and greppable across every bounded context and every API response — the
concrete mechanism behind the API Foundation's standard error response
(platform_core.api.responses) and the Error Handling module's error mapping.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    # Generic / cross-cutting
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"

    # Concurrency
    OPTIMISTIC_LOCK_FAILED = "OPTIMISTIC_LOCK_FAILED"

    # Infrastructure
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    MESSAGE_PUBLISH_FAILED = "MESSAGE_PUBLISH_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"
