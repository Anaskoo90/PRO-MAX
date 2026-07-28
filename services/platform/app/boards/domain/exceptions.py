"""Boards & Agile Management domain exceptions, layered on platform_core's
exception hierarchy exactly like every prior context's do."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError, EntityNotFoundError
from app.platform_core.shared_kernel.error_codes import ErrorCode


class BoardNotFoundError(EntityNotFoundError):
    def __init__(self, board_id: object) -> None:
        super().__init__("Board", board_id)


class BoardNotActiveError(BusinessRuleViolationError):
    def __init__(self, status: str) -> None:
        super().__init__("board_not_active", f"Board status '{status}' does not permit this action")


class BoardAlreadyArchivedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("board_already_archived", "This board is already archived")


class BoardNotArchivedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("board_not_archived", "This board is not archived")


class BoardAlreadyDeletedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("board_already_deleted", "This board has already been deleted")


class ColumnNotFoundError(EntityNotFoundError):
    def __init__(self, column_id: object) -> None:
        super().__init__("Column", column_id)


class ColumnNameAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self, name: str) -> None:
        super().__init__("column_name_already_exists", f"A column named '{name}' already exists on this board")


class WipLimitExceededError(BusinessRuleViolationError):
    def __init__(self, column_name: str, wip_limit: int, current_count: int) -> None:
        super().__init__(
            "wip_limit_exceeded",
            f"Column '{column_name}' has a WIP limit of {wip_limit} and already has {current_count} card(s)",
        )


class InvalidWipLimitError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("invalid_wip_limit", "WIP limit must be a positive integer or unset")


class InvalidColumnColorError(BusinessRuleViolationError):
    def __init__(self, color: str) -> None:
        super().__init__("invalid_column_color", f"'{color}' is not a valid hex color (expected e.g. '#3B82F6')")


class SwimlaneNotFoundError(EntityNotFoundError):
    def __init__(self, swimlane_id: object) -> None:
        super().__init__("Swimlane", swimlane_id)


class CustomSwimlaneRequiredError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "custom_swimlane_required", "Custom swimlanes can only be created when the board's strategy is 'custom'"
        )


class BoardCardNotFoundError(EntityNotFoundError):
    def __init__(self, card_id: object) -> None:
        super().__init__("BoardCard", card_id)


class TaskAlreadyOnBoardError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_already_on_board", "This task is already placed on this board")


class TaskNotAccessibleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, task_id: object) -> None:
        super().__init__("task_not_accessible", f"Task '{task_id}' was not found or is not accessible")


class InvalidEstimateError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_estimate", reason)


class SprintNotFoundError(EntityNotFoundError):
    def __init__(self, sprint_id: object) -> None:
        super().__init__("Sprint", sprint_id)


class InvalidSprintTransitionError(BusinessRuleViolationError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            "invalid_sprint_transition", f"Cannot transition sprint from '{current_status}' to '{target_status}'"
        )


class InvalidSprintDateRangeError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_sprint_date_range", reason)


class OnlyOneActiveSprintPerBoardError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("only_one_active_sprint_per_board", "This board already has an active sprint")


class InsufficientBoardPermissionError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, required: tuple[str, ...]) -> None:
        super().__init__("insufficient_board_permission", f"This action requires one of: {', '.join(required)}")


class ProjectNotAccessibleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, project_id: object) -> None:
        super().__init__("project_not_accessible", f"Project '{project_id}' was not found or is not accessible")
