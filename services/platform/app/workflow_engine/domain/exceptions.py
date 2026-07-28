"""Workflow Engine domain exceptions, layered on platform_core's exception
hierarchy exactly like every prior context's do."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError, EntityNotFoundError
from app.platform_core.shared_kernel.error_codes import ErrorCode


class WorkflowNotFoundError(EntityNotFoundError):
    def __init__(self, workflow_id: object) -> None:
        super().__init__("Workflow", workflow_id)


class WorkflowNotActiveError(BusinessRuleViolationError):
    def __init__(self, status: str) -> None:
        super().__init__("workflow_not_active", f"Workflow status '{status}' does not permit this action")


class WorkflowAlreadyArchivedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("workflow_already_archived", "This workflow is already archived")


class WorkflowNotArchivedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("workflow_not_archived", "This workflow is not archived")


class WorkflowAlreadyDeletedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("workflow_already_deleted", "This workflow has already been deleted")


class StateNotFoundError(EntityNotFoundError):
    def __init__(self, state_id: object) -> None:
        super().__init__("WorkflowState", state_id)


class StateNameAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self, name: str) -> None:
        super().__init__("state_name_already_exists", f"A state named '{name}' already exists on this workflow")


class StateInUseError(BusinessRuleViolationError):
    def __init__(self, state_id: object) -> None:
        super().__init__("state_in_use", f"State '{state_id}' is referenced by a transition and cannot be deleted")


class TransitionNotFoundError(EntityNotFoundError):
    def __init__(self, transition_id: object) -> None:
        super().__init__("WorkflowTransition", transition_id)


class TransitionDisabledError(BusinessRuleViolationError):
    def __init__(self, transition_id: object) -> None:
        super().__init__("transition_disabled", f"Transition '{transition_id}' is disabled")


class InvalidTransitionError(BusinessRuleViolationError):
    def __init__(self, current_state_id: object, transition_id: object) -> None:
        super().__init__(
            "invalid_transition", f"Transition '{transition_id}' cannot be applied from the task's current state '{current_state_id}'"
        )


class TaskNotEnrolledError(BusinessRuleViolationError):
    def __init__(self, task_id: object) -> None:
        super().__init__("task_not_enrolled", f"Task '{task_id}' is not enrolled in this workflow")


class TaskAlreadyEnrolledError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_already_enrolled", "This task is already enrolled in this workflow")


class WorkflowHasNoInitialStateError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("workflow_has_no_initial_state", "This workflow has no initial state configured yet")


class RuleNotFoundError(EntityNotFoundError):
    def __init__(self, rule_id: object) -> None:
        super().__init__("TransitionRule", rule_id)


class ConditionNotFoundError(EntityNotFoundError):
    def __init__(self, condition_id: object) -> None:
        super().__init__("WorkflowCondition", condition_id)


class ActionNotFoundError(EntityNotFoundError):
    def __init__(self, action_id: object) -> None:
        super().__init__("WorkflowAction", action_id)


class RequiredRoleNotMetError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, required_roles: tuple[str, ...]) -> None:
        super().__init__("required_role_not_met", f"This transition requires one of: {', '.join(required_roles)}")


class RequiredPermissionNotMetError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, resource: str, action: str) -> None:
        super().__init__("required_permission_not_met", f"This transition requires permission '{resource}:{action}'")


class RequiredFieldValueNotMetError(BusinessRuleViolationError):
    def __init__(self, field_name: str, expected: object) -> None:
        super().__init__("required_field_value_not_met", f"Field '{field_name}' must equal '{expected}' for this transition")


class UnsupportedWorkflowFieldError(BusinessRuleViolationError):
    def __init__(self, field_name: str) -> None:
        super().__init__(
            "unsupported_workflow_field",
            f"'{field_name}' is not a field Workflow Engine can evaluate — no bounded context exposes it yet",
        )


class ApprovalRequiredError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("approval_required", "This transition requires an approved approval request first")


class ApprovalNotFoundError(EntityNotFoundError):
    def __init__(self, approval_id: object) -> None:
        super().__init__("WorkflowApprovalRequest", approval_id)


class ApprovalAlreadyDecidedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("approval_already_decided", "This approval request has already been decided")


class ChecklistIncompleteError(BusinessRuleViolationError):
    def __init__(self, remaining: int) -> None:
        super().__init__("checklist_incomplete", f"{remaining} required checklist item(s) are not yet completed")


class ChecklistItemNotFoundError(EntityNotFoundError):
    def __init__(self, item_id: object) -> None:
        super().__init__("WorkflowChecklistItem", item_id)


class ConditionsNotMetError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("conditions_not_met", "One or more conditions attached to this transition were not satisfied")


class InsufficientWorkflowPermissionError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, required: tuple[str, ...]) -> None:
        super().__init__("insufficient_workflow_permission", f"This action requires one of: {', '.join(required)}")


class ProjectNotAccessibleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, project_id: object) -> None:
        super().__init__("project_not_accessible", f"Project '{project_id}' was not found or is not accessible")


class TaskNotAccessibleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, task_id: object) -> None:
        super().__init__("task_not_accessible", f"Task '{task_id}' was not found or is not accessible")


class WebhookExecutionFailedError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("webhook_execution_failed", reason)
