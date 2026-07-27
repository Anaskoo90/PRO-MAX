"""
Global Exception Handling + Error Mapping: registered once on the FastAPI
app in the composition root (app/main.py). Maps the platform's exception
hierarchy to HTTP responses so individual route handlers never write
try/except-to-HTTPException boilerplate.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.platform_core.errors.api_exceptions import ApiError
from app.platform_core.errors.domain_exceptions import (
    BusinessRuleViolationError,
    ConcurrencyConflictError,
    EntityNotFoundError,
)
from app.platform_core.errors.infrastructure_exceptions import InfrastructureError
from app.platform_core.errors.responses import ErrorDetail, ErrorResponse
from app.platform_core.logging.logger import get_logger
from app.platform_core.shared_kernel.error_codes import ErrorCode
from app.platform_core.shared_kernel.exceptions import GuildDeskError

_logger = get_logger("errors")

_DOMAIN_STATUS_MAP: dict[type[GuildDeskError], int] = {
    EntityNotFoundError: status.HTTP_404_NOT_FOUND,
    BusinessRuleViolationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ConcurrencyConflictError: status.HTTP_409_CONFLICT,
}


def _map_status_code(exc: GuildDeskError) -> int:
    if isinstance(exc, ApiError):
        return exc.http_status
    for exc_type, http_status in _DOMAIN_STATUS_MAP.items():
        if isinstance(exc, exc_type):
            return http_status
    if isinstance(exc, InfrastructureError):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_500_INTERNAL_SERVER_ERROR


async def _handle_guilddesk_error(request: Request, exc: GuildDeskError) -> JSONResponse:
    http_status = _map_status_code(exc)
    if http_status >= 500:
        await _logger.aerror("unhandled_platform_error", error=str(exc), exc_info=True)
    else:
        await _logger.awarn("handled_platform_error", code=exc.code, error=str(exc))
    return JSONResponse(
        status_code=http_status,
        content=ErrorResponse.build(exc.code, exc.message).model_dump(mode="json"),
    )


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        ErrorDetail(field=".".join(str(p) for p in e["loc"]), message=e["msg"])
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse.build(
            ErrorCode.VALIDATION_FAILED, "Request validation failed", details
        ).model_dump(mode="json"),
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    await _logger.aerror("unhandled_exception", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse.build(
            ErrorCode.INTERNAL_ERROR, "An unexpected error occurred"
        ).model_dump(mode="json"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GuildDeskError, _handle_guilddesk_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
