"""
Anti-Corruption Layer: the only file in this bounded context permitted to
depend on Projects & Workspaces. Wraps Projects' own public application
services (ProjectService, ProjectMembershipService — not infrastructure)
and translates their DTOs into this context's own ProjectSummary/
ProjectMemberSummary (application.ports). Structurally identical to
Tasks' own ProjectsProjectContextAdapter — each context builds its own
ACL to Projects rather than importing another context's ACL.
"""

from __future__ import annotations

from uuid import UUID

from app.projects.application.membership_management import ProjectMembershipService
from app.projects.application.project_management import ProjectService
from app.projects.domain.exceptions import ProjectNotFoundError as ProjectsProjectNotFoundError
from app.boards.application.ports import ProjectMemberSummary, ProjectSummary


class ProjectsProjectContextAdapter:
    def __init__(self, *, project_service: ProjectService, project_membership_service: ProjectMembershipService) -> None:
        self._project_service = project_service
        self._project_membership_service = project_membership_service

    async def get_project(self, *, project_id: UUID) -> ProjectSummary | None:
        try:
            project = await self._project_service.get(project_id=project_id)
        except ProjectsProjectNotFoundError:
            return None
        return ProjectSummary(id=project.id, org_id=project.org_id, workspace_id=project.workspace_id, status=project.status)

    async def get_member(self, *, project_id: UUID, user_id: UUID) -> ProjectMemberSummary | None:
        members = await self._project_membership_service.list_members(project_id=project_id)
        match = next((m for m in members if m.user_id == user_id), None)
        if match is None:
            return None
        return ProjectMemberSummary(user_id=match.user_id, role=match.role, status=match.status)

    async def list_members(self, *, project_id: UUID) -> list[ProjectMemberSummary]:
        members = await self._project_membership_service.list_members(project_id=project_id)
        return [ProjectMemberSummary(user_id=m.user_id, role=m.role, status=m.status) for m in members]
