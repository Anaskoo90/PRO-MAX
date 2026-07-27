"""Projects & Workspaces domain exceptions, layered on platform_core's
exception hierarchy exactly like Identity's do — the global exception
handler (platform_core.errors.handlers) maps these without any
context-specific handler registration."""

from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError, EntityNotFoundError
from app.platform_core.shared_kernel.error_codes import ErrorCode


class WorkspaceNotFoundError(EntityNotFoundError):
    def __init__(self, workspace_id: object) -> None:
        super().__init__("Workspace", workspace_id)


class WorkspaceNotActiveError(BusinessRuleViolationError):
    def __init__(self, status: str) -> None:
        super().__init__("workspace_not_active", f"Workspace status '{status}' does not permit this action")


class WorkspaceSlugTakenError(BusinessRuleViolationError):
    def __init__(self, slug: str) -> None:
        super().__init__("workspace_slug_taken", f"Slug '{slug}' is already in use in this organization")


class InvalidWorkspaceSlugError(BusinessRuleViolationError):
    def __init__(self, slug: str) -> None:
        super().__init__("invalid_workspace_slug", f"'{slug}' is not a valid workspace slug")


class WorkspaceMembershipNotFoundError(EntityNotFoundError):
    def __init__(self, workspace_id: object, user_id: object) -> None:
        super().__init__("WorkspaceMembership", f"{workspace_id}:{user_id}")


class WorkspaceMembershipAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("workspace_membership_exists", "User is already a member of this workspace")


class ProjectNotFoundError(EntityNotFoundError):
    def __init__(self, project_id: object) -> None:
        super().__init__("Project", project_id)


class ProjectAlreadyDeletedError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("project_already_deleted", "This project has already been deleted")


class InvalidProjectStatusTransitionError(BusinessRuleViolationError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            "invalid_project_status_transition",
            f"Cannot transition project from '{current_status}' to '{target_status}'",
        )


class ProjectMembershipNotFoundError(EntityNotFoundError):
    def __init__(self, project_id: object, user_id: object) -> None:
        super().__init__("ProjectMembership", f"{project_id}:{user_id}")


class ProjectMembershipAlreadyExistsError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__("project_membership_exists", "User is already a member (or has a pending invite) for this project")


class CannotRemoveLastProjectOwnerError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "cannot_remove_last_owner", "A project must always have at least one owner"
        )


class UserNotInOrganizationError(BusinessRuleViolationError):
    def __init__(self, email: str) -> None:
        super().__init__("user_not_in_organization", f"No organization member was found with email '{email}'")


class ProjectTemplateNotFoundError(EntityNotFoundError):
    def __init__(self, template_id: object) -> None:
        super().__init__("ProjectTemplate", template_id)


class InvalidTemplateImportError(BusinessRuleViolationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_template_import", f"Template import payload is invalid: {reason}")


class InsufficientProjectRoleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self, required_roles: tuple[str, ...]) -> None:
        super().__init__(
            "insufficient_project_role",
            f"This action requires one of the following project roles: {', '.join(required_roles)}",
        )
