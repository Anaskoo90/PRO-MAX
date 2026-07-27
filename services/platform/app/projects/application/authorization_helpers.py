"""
Shared authorization helpers used by every service in this context.

Two independent gates, deliberately not merged into one check:
- Org-wide capability ("can this user create a workspace at all") — goes
  through OrgPermissionCheckerPort, i.e. Identity's RBAC.
- Local, instance-scoped role ("is this user an owner/admin of *this*
  workspace/project") — this context's own WorkspaceMembership/
  ProjectMembership, since Identity's RBAC has no concept of a workspace or
  project.

An action is authorized if *either* gate passes — an org admin can manage
any workspace/project without being an explicit member, and a workspace/
project owner can manage their own without needing an org-wide grant.
"""

from __future__ import annotations

from app.projects.application.ports import OrgPermissionCheckerPort, ProjectsUnitOfWorkPort
from app.projects.domain.entities import ProjectRole, WorkspaceRole
from app.projects.domain.exceptions import InsufficientProjectRoleError, WorkspaceNotActiveError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class WorkspaceAuthorization:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort) -> None:
        self._permission_checker = permission_checker

    async def can_manage(
        self, *, uow: ProjectsUnitOfWorkPort, workspace_id: EntityId, org_id: OrgId, user_id: UserId
    ) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="workspace", action="update"):
            return True
        membership = await uow.workspace_memberships.get(workspace_id, user_id)
        return membership is not None and membership.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    async def can_create_projects(
        self, *, uow: ProjectsUnitOfWorkPort, workspace_id: EntityId, org_id: OrgId, user_id: UserId
    ) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="project", action="create"):
            return True
        membership = await uow.workspace_memberships.get(workspace_id, user_id)
        return membership is not None and membership.role != WorkspaceRole.VIEWER


class ProjectAuthorization:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort) -> None:
        self._permission_checker = permission_checker

    async def can_manage(
        self, *, uow: ProjectsUnitOfWorkPort, project_id: EntityId, org_id: OrgId, user_id: UserId
    ) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="project", action="update"):
            return True
        membership = await uow.project_memberships.get(project_id, user_id)
        return membership is not None and membership.role in (ProjectRole.OWNER, ProjectRole.ADMIN) and membership.status.value == "active"

    async def can_manage_members(
        self, *, uow: ProjectsUnitOfWorkPort, project_id: EntityId, org_id: OrgId, user_id: UserId
    ) -> bool:
        if await self._permission_checker.has_permission(user_id=user_id, org_id=org_id, resource="project", action="manage_members"):
            return True
        return await self.can_manage(uow=uow, project_id=project_id, org_id=org_id, user_id=user_id)

    async def assert_can_manage(self, *, uow: ProjectsUnitOfWorkPort, project_id: EntityId, org_id: OrgId, user_id: UserId) -> None:
        if not await self.can_manage(uow=uow, project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientProjectRoleError(("owner", "admin"))

    async def assert_can_manage_members(
        self, *, uow: ProjectsUnitOfWorkPort, project_id: EntityId, org_id: OrgId, user_id: UserId
    ) -> None:
        if not await self.can_manage_members(uow=uow, project_id=project_id, org_id=org_id, user_id=user_id):
            raise InsufficientProjectRoleError(("owner", "admin"))
