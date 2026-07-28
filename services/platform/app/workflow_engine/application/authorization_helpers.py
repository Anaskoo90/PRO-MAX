"""
Shared authorization helper used by every service in this context.

Workflows have no membership concept of their own — a workflow belongs to
a Project, and "can this user touch this workflow" reduces to their
Project membership role (via ProjectContextPort, the ACL over Projects &
Workspaces) plus the usual org-wide RBAC escape hatch (via
OrgPermissionCheckerPort, i.e. Identity's RBAC). Same two-gate pattern
Projects, Tasks, and Boards all already established.
"""

from __future__ import annotations

from app.workflow_engine.application.ports import OrgPermissionCheckerPort, ProjectContextPort, ProjectSummary
from app.workflow_engine.domain.exceptions import InsufficientWorkflowPermissionError, ProjectNotAccessibleError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId

_MANAGING_ROLES = ("owner", "admin", "contributor")


class WorkflowAuthorization:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort, project_context: ProjectContextPort) -> None:
        self._permission_checker = permission_checker
        self._project_context = project_context

    async def assert_project_accessible(self, *, project_id: EntityId, org_id: OrgId) -> ProjectSummary:
        project = await self._project_context.get_project(project_id=project_id)
        if project is None or project.org_id != org_id:
            raise ProjectNotAccessibleError(project_id)
        return project

    async def _has_project_role(self, *, project_id: EntityId, user_id: UserId) -> bool:
        member = await self._project_context.get_member(project_id=project_id, user_id=user_id)
        return member is not None and member.status == "active" and member.role in _MANAGING_ROLES

    async def can_view(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="workflow", action="view"):
            return True
        member = await self._project_context.get_member(project_id=project_id, user_id=user_id)
        return member is not None and member.status == "active"

    async def can_manage(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="workflow", action="manage"):
            return True
        return await self._has_project_role(project_id=project_id, user_id=user_id)

    async def can_execute(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="workflow", action="execute"):
            return True
        return await self._has_project_role(project_id=project_id, user_id=user_id)

    async def can_manage_automation(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="workflow", action="manage_automation"):
            return True
        return await self._has_project_role(project_id=project_id, user_id=user_id)

    async def assert_can_manage(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> None:
        if not await self.can_manage(project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientWorkflowPermissionError(_MANAGING_ROLES)

    async def assert_can_execute(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> None:
        if not await self.can_execute(project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientWorkflowPermissionError(_MANAGING_ROLES)

    async def assert_can_manage_automation(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> None:
        if not await self.can_manage_automation(project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientWorkflowPermissionError(_MANAGING_ROLES)
