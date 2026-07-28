"""Tasks & Work Management domain exceptions, layered on platform_core's
exception hierarchy exactly like Identity's and Projects' do."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError, EntityNotFoundError
from app.platform_core.shared_kernel.error_codes import ErrorCode


class TaskNotFoundError(EntityNotFoundError):
    def __init__(self, task_id: object) -> None:
        super().__init__("Task", task_id)


class TaskAlreadyDeletedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_already_deleted", "This task has already been deleted")


class TaskNotArchivedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_not_archived", "This task is not archived")


class TaskAlreadyArchivedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_already_archived", "This task is already archived")


class InvalidTaskStatusTransitionError(BusinessRuleViolationError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            "invalid_task_status_transition",
            f"Cannot transition task from '{current_status}' to '{target_status}' under the active workflow",
        )


class InvalidDateRangeError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_date_range", reason)


class TaskParentCycleError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_parent_cycle", "This would create a cycle in the parent/subtask hierarchy")


class TaskCannotBeOwnParentError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_cannot_be_own_parent", "A task cannot be its own parent")


class TaskDependencyCycleError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_dependency_cycle", "This would create a cycle in the task dependency graph")


class TaskCannotDependOnItselfError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_cannot_depend_on_itself", "A task cannot depend on itself")


class TaskDependencyAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_dependency_already_exists", "This dependency already exists")


class TaskDependencyNotFoundError(EntityNotFoundError):
    def __init__(self, task_id: object, depends_on_task_id: object) -> None:
        super().__init__("TaskDependency", f"{task_id}:{depends_on_task_id}")


class TaskRelationAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_relation_already_exists", "This related-task link already exists")


class TaskRelationNotFoundError(EntityNotFoundError):
    def __init__(self, task_id: object, related_task_id: object) -> None:
        super().__init__("TaskRelation", f"{task_id}:{related_task_id}")


class TaskAssignmentNotFoundError(EntityNotFoundError):
    def __init__(self, task_id: object, user_id: object) -> None:
        super().__init__("TaskAssignment", f"{task_id}:{user_id}")


class TaskAlreadyAssignedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_already_assigned", "This user is already assigned to this task")


class LabelNotFoundError(EntityNotFoundError):
    def __init__(self, label_id: object) -> None:
        super().__init__("Label", label_id)


class LabelAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self, name: str) -> None:
        super().__init__("label_already_exists", f"A label named '{name}' already exists in this project")


class InvalidLabelColorError(BusinessRuleViolationError):
    def __init__(self, color: str) -> None:
        super().__init__("invalid_label_color", f"'{color}' is not a valid hex color (expected e.g. '#3B82F6')")


class TaskLabelAlreadyAttachedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("task_label_already_attached", "This label is already attached to this task")


class WorkflowDefinitionNotFoundError(EntityNotFoundError):
    def __init__(self, workflow_id: object) -> None:
        super().__init__("WorkflowDefinition", workflow_id)


class InvalidWorkflowDefinitionError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_workflow_definition", reason)


class InsufficientTaskPermissionError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, required: tuple[str, ...]) -> None:
        super().__init__(
            "insufficient_task_permission", f"This action requires one of: {', '.join(required)}"
        )


class ProjectNotAccessibleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, project_id: object) -> None:
        super().__init__("project_not_accessible", f"Project '{project_id}' was not found or is not accessible")


class UserNotInOrganizationError(BusinessRuleViolationError):
    def __init__(self, user_id: object) -> None:
        super().__init__(
            "user_not_in_organization", f"User '{user_id}' is not an active member of this task's project"
        )
