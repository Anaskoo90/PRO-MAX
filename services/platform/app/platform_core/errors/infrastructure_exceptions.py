from __future__ import annotations

from app.platform_core.shared_kernel.error_codes import ErrorCode
from app.platform_core.shared_kernel.exceptions import GuildDeskError


class InfrastructureError(GuildDeskError):
    code = ErrorCode.DEPENDENCY_UNAVAILABLE


class DatabaseError(InfrastructureError):
    pass


class MessagePublishError(InfrastructureError):
    code = ErrorCode.MESSAGE_PUBLISH_FAILED


class StorageError(InfrastructureError):
    code = ErrorCode.STORAGE_FAILED


class ExternalServiceTimeoutError(InfrastructureError):
    code = ErrorCode.TIMEOUT

    def __init__(self, service_name: str, timeout_seconds: float) -> None:
        super().__init__(f"Call to '{service_name}' timed out after {timeout_seconds}s")
        self.service_name = service_name


class CircuitOpenError(InfrastructureError):
    code = ErrorCode.UNAVAILABLE

    def __init__(self, service_name: str) -> None:
        super().__init__(f"Circuit breaker for '{service_name}' is open")
        self.service_name = service_name
