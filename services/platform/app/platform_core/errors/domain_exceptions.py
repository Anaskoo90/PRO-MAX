"""
Domain Exceptions: raised by domain/application layers for genuinely
exceptional conditions. Expected business-rule failures should generally
prefer shared_kernel.result.Err over raising — these exist for invariant
violations that indicate a programming error or a race the Result pattern
isn't meant to model.
"""

from __future__ import annotations

from app.platform_core.shared_kernel.error_codes import ErrorCode
from app.platform_core.shared_kernel.exceptions import GuildDeskError


class DomainError(GuildDeskError):
    pass


class EntityNotFoundError(DomainError):
    code = ErrorCode.NOT_FOUND

    def __init__(self, entity_name: str, entity_id: object) -> None:
        super().__init__(f"{entity_name} '{entity_id}' was not found")
        self.entity_name = entity_name
        self.entity_id = entity_id


class BusinessRuleViolationError(DomainError):
    code = ErrorCode.VALIDATION_FAILED

    def __init__(self, rule_name: str, message: str) -> None:
        super().__init__(message)
        self.rule_name = rule_name


class ConcurrencyConflictError(DomainError):
    """Raised when an optimistic-lock version check fails on update."""

    code = ErrorCode.OPTIMISTIC_LOCK_FAILED

    def __init__(self, entity_name: str, entity_id: object) -> None:
        super().__init__(f"{entity_name} '{entity_id}' was modified concurrently")
