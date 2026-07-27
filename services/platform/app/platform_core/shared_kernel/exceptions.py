"""
Root exception type for the platform.

This is the *base* of the hierarchy only. Concrete domain / infrastructure /
API exception subclasses live in platform_core.errors — kept there, not
here, so shared_kernel (imported by domain layers) never pulls in the
FastAPI-facing error-mapping machinery.
"""

from __future__ import annotations

from app.platform_core.shared_kernel.error_codes import ErrorCode


class GuildDeskError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str, *, code: ErrorCode | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
