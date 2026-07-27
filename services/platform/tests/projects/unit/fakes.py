"""In-memory fakes satisfying the Projects & Workspaces repository
Protocols and application ports — used to unit-test application-layer
services without a real database, mirroring tests/identity/unit/fakes.py."""

from __future__ import annotations

from app.projects.application.ports import UserSummary
from app.projects.domain.entities import Project, ProjectMembership, ProjectRole, ProjectTemplate, Workspace, WorkspaceMembership
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class FakeWorkspaceRepository:
    def __init__(self) -> None:
        self.workspaces: dict[EntityId, Workspace] = {}

    async def get_by_id(self, workspace_id: EntityId) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    async def get_by_slug(self, org_id: OrgId, slug: str) -> Workspace | None:
        return next((w for w in self.workspaces.values() if w.org_id == org_id and w.slug == slug), None)

    async def list_for_org(self, org_id: OrgId) -> list[Workspace]:
        return [w for w in self.workspaces.values() if w.org_id == org_id]

    async def add(self, workspace: Workspace) -> None:
        self.workspaces[workspace.id] = workspace

    async def update(self, workspace: Workspace) -> None:
        self.workspaces[workspace.id] = workspace


class FakeWorkspaceMembershipRepository:
    def __init__(self) -> None:
        self.memberships: list[WorkspaceMembership] = []

    async def get(self, workspace_id: EntityId, user_id: UserId) -> WorkspaceMembership | None:
        return next((m for m in self.memberships if m.workspace_id == workspace_id and m.user_id == user_id), None)

    async def list_for_workspace(self, workspace_id: EntityId) -> list[WorkspaceMembership]:
        return [m for m in self.memberships if m.workspace_id == workspace_id]

    async def list_for_user(self, user_id: UserId) -> list[WorkspaceMembership]:
        return [m for m in self.memberships if m.user_id == user_id]

    async def add(self, membership: WorkspaceMembership) -> None:
        self.memberships.append(membership)

    async def update(self, membership: WorkspaceMembership) -> None:
        pass

    async def delete(self, membership_id: EntityId) -> None:
        self.memberships = [m for m in self.memberships if m.id != membership_id]


class FakeProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[EntityId, Project] = {}

    async def get_by_id(self, project_id: EntityId) -> Project | None:
        return self.projects.get(project_id)

    async def list_for_workspace(self, workspace_id: EntityId, *, include_archived: bool = False) -> list[Project]:
        return [p for p in self.projects.values() if p.workspace_id == workspace_id]

    async def add(self, project: Project) -> None:
        self.projects[project.id] = project

    async def update(self, project: Project) -> None:
        self.projects[project.id] = project


class FakeProjectMembershipRepository:
    def __init__(self) -> None:
        self.memberships: list[ProjectMembership] = []

    async def get(self, project_id: EntityId, user_id: UserId) -> ProjectMembership | None:
        return next((m for m in self.memberships if m.project_id == project_id and m.user_id == user_id), None)

    async def list_for_project(self, project_id: EntityId) -> list[ProjectMembership]:
        return [m for m in self.memberships if m.project_id == project_id]

    async def list_for_user(self, user_id: UserId) -> list[ProjectMembership]:
        return [m for m in self.memberships if m.user_id == user_id]

    async def count_owners(self, project_id: EntityId) -> int:
        return sum(
            1 for m in self.memberships
            if m.project_id == project_id and m.role == ProjectRole.OWNER and m.status.value == "active"
        )

    async def add(self, membership: ProjectMembership) -> None:
        self.memberships.append(membership)

    async def update(self, membership: ProjectMembership) -> None:
        pass

    async def delete(self, membership_id: EntityId) -> None:
        self.memberships = [m for m in self.memberships if m.id != membership_id]


class FakeProjectTemplateRepository:
    def __init__(self) -> None:
        self.templates: dict[EntityId, ProjectTemplate] = {}

    async def get_by_id(self, template_id: EntityId) -> ProjectTemplate | None:
        return self.templates.get(template_id)

    async def list_for_org(self, org_id: OrgId) -> list[ProjectTemplate]:
        return [t for t in self.templates.values() if t.org_id == org_id]

    async def get_default(self, org_id: OrgId) -> ProjectTemplate | None:
        return next((t for t in self.templates.values() if t.org_id == org_id and t.is_default), None)

    async def add(self, template: ProjectTemplate) -> None:
        self.templates[template.id] = template

    async def update(self, template: ProjectTemplate) -> None:
        self.templates[template.id] = template

    async def delete(self, template_id: EntityId) -> None:
        self.templates.pop(template_id, None)


class FakeProjectsAuditLogRepository:
    def __init__(self) -> None:
        self.records: list = []

    async def add(self, record) -> None:
        self.records.append(record)

    async def list_for_org(self, org_id, *, category=None, limit: int = 50):
        results = [r for r in self.records if r.org_id == org_id]
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:limit]


class FakeOutboxWriter:
    async def append(self, event) -> None:
        pass


class FakeProjectsUnitOfWork:
    def __init__(self) -> None:
        self.workspaces = FakeWorkspaceRepository()
        self.workspace_memberships = FakeWorkspaceMembershipRepository()
        self.projects = FakeProjectRepository()
        self.project_memberships = FakeProjectMembershipRepository()
        self.project_templates = FakeProjectTemplateRepository()
        self.audit_logs = FakeProjectsAuditLogRepository()
        self.outbox = FakeOutboxWriter()

    async def __aenter__(self) -> "FakeProjectsUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class AllowAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return True


class DenyAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return False


class FakeUserDirectory:
    def __init__(self, users: dict[str, UserSummary] | None = None) -> None:
        self.by_email = users or {}

    async def find_by_email(self, *, org_id, email: str):
        return self.by_email.get(email)

    async def get_by_id(self, *, user_id):
        return next((u for u in self.by_email.values() if u.id == user_id), None)
