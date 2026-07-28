"""
Shared authorization helper used by every service in this context.

Tasks have no membership concept of their own — a task belongs to a
Project, and "can this user touch this task" reduces to "what's their
Project membership role" (via ProjectContextPort, the ACL over Projects &
Workspaces) plus the usual org-wide RBAC escape hatch (via
OrgPermissionCheckerPort, i.e. Identity's RBAC) for org admins who aren't
explicit project members. Same two-gate pattern Projects & Workspaces
established for its own workspace/project authorization.
"""

from __future__ import annotations

from app.tasks.application.ports import OrgPermissionCheckerPort, ProjectContextPort, ProjectSummary
from app.tasks.domain.exceptions import InsufficientTaskPermissionError, ProjectNotAccessibleError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId

_MANAGING_ROLES = ("owner", "admin", "contributor")


class TaskAuthorization:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort, project_context: ProjectContextPort) -> None:
        self._permission_checker = permission_checker
        self._project_context = project_context

    async def assert_project_accessible(self, *, project_id: EntityId, org_id: OrgId) -> ProjectSummary:
        project = await self._project_context.get_project(project_id=project_id)
        if project is None or project.org_id != org_id:
            raise ProjectNotAccessibleError(project_id)
        return project

    async def can_manage(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="task", action="update"):
            return True
        member = await self._project_context.get_member(project_id=project_id, user_id=user_id)
        return member is not None and member.status == "active" and member.role in _MANAGING_ROLES

    async def can_view(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="task", action="read"):
            return True
        member = await self._project_context.get_member(project_id=project_id, user_id=user_id)
        return member is not None and member.status == "active"

    async def assert_can_manage(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> None:
        if not await self.can_manage(project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientTaskPermissionError(_MANAGING_ROLES)

    async def assert_can_view(self, *, project_id: EntityId, org_id: OrgId, user_id: UserId) -> None:
        if not await self.can_view(project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientTaskPermissionError(("any active project member",))
