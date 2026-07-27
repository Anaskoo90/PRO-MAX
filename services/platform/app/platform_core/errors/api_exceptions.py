from __future__ import annotations

from app.platform_core.shared_kernel.error_codes import ErrorCode
from app.platform_core.shared_kernel.exceptions import GuildDeskError


class ApiError(GuildDeskError):
    """Base for exceptions meant to terminate directly in an HTTP response."""

    http_status: int = 500


class UnauthorizedError(ApiError):
    code = ErrorCode.UNAUTHORIZED
    http_status = 401


class ForbiddenError(ApiError):
    code = ErrorCode.FORBIDDEN
    http_status = 403


class RateLimitedError(ApiError):
    code = ErrorCode.RATE_LIMITED
    http_status = 429

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds
