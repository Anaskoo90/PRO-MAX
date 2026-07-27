"""Standard Error Responses: one shape for every error the API ever returns."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.platform_core.logging.correlation import get_correlation_id
from app.platform_core.shared_kernel.error_codes import ErrorCode


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str
    correlation_id: str | None = None
    details: list[ErrorDetail] = []

    @classmethod
    def build(
        cls,
        code: ErrorCode,
        message: str,
        details: list[ErrorDetail] | None = None,
    ) -> "ErrorResponse":
        return cls(
            code=code,
            message=message,
            correlation_id=get_correlation_id(),
            details=details or [],
        )
