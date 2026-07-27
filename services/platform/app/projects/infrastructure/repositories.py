"""SQLAlchemy-backed implementations of the Projects & Workspaces repository Protocols."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.domain.audit import ProjectsAuditEventCategory, ProjectsAuditLogRecord
from app.projects.domain.entities import (
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectTemplate,
    Workspace,
    WorkspaceMembership,
)
from app.projects.infrastructure import mappers
from app.projects.infrastructure.orm_models import (
    ProjectMembershipOrmModel,
    ProjectOrmModel,
    ProjectsAuditLogOrmModel,
    ProjectTemplateOrmModel,
    WorkspaceMembershipOrmModel,
    WorkspaceOrmModel,
)
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


class SqlAlchemyWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id: EntityId) -> Workspace | None:
        row = await self._session.get(WorkspaceOrmModel, workspace_id)
        return mappers.workspace_to_domain(row) if row and row.deleted_at is None else None

    async def get_by_slug(self, org_id: OrgId, slug: str) -> Workspace | None:
        stmt = select(WorkspaceOrmModel).where(
            WorkspaceOrmModel.org_id == org_id, WorkspaceOrmModel.slug == slug, WorkspaceOrmModel.deleted_at.is_(None)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.workspace_to_domain(row) if row else None

    async def list_for_org(self, org_id: OrgId) -> list[Workspace]:
        stmt = select(WorkspaceOrmModel).where(
            WorkspaceOrmModel.org_id == org_id, WorkspaceOrmModel.deleted_at.is_(None)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.workspace_to_domain(r) for r in rows]

    async def add(self, workspace: Workspace) -> None:
        self._session.add(mappers.workspace_to_orm(workspace))

    async def update(self, workspace: Workspace) -> None:
        row = await self._session.get(WorkspaceOrmModel, workspace.id)
        if row is None:
            raise ValueError(f"Workspace {workspace.id} not found for update")
        if row.version != workspace.version:
            raise ConcurrencyConflictError("Workspace", workspace.id)
        mappers.workspace_to_orm(workspace, row)
        row.version = workspace.version + 1
        workspace.version += 1


class SqlAlchemyWorkspaceMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workspace_id: EntityId, user_id: UserId) -> WorkspaceMembership | None:
        stmt = select(WorkspaceMembershipOrmModel).where(
            WorkspaceMembershipOrmModel.workspace_id == workspace_id, WorkspaceMembershipOrmModel.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.workspace_membership_to_domain(row) if row else None

    async def list_for_workspace(self, workspace_id: EntityId) -> list[WorkspaceMembership]:
        stmt = select(WorkspaceMembershipOrmModel).where(WorkspaceMembershipOrmModel.workspace_id == workspace_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.workspace_membership_to_domain(r) for r in rows]

    async def list_for_user(self, user_id: UserId) -> list[WorkspaceMembership]:
        stmt = select(WorkspaceMembershipOrmModel).where(WorkspaceMembershipOrmModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.workspace_membership_to_domain(r) for r in rows]

    async def add(self, membership: WorkspaceMembership) -> None:
        self._session.add(mappers.workspace_membership_to_orm(membership))

    async def update(self, membership: WorkspaceMembership) -> None:
        row = await self._session.get(WorkspaceMembershipOrmModel, membership.id)
        if row is None:
            raise ValueError(f"WorkspaceMembership {membership.id} not found for update")
        row.role = membership.role.value

    async def delete(self, membership_id: EntityId) -> None:
        row = await self._session.get(WorkspaceMembershipOrmModel, membership_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: EntityId) -> Project | None:
        row = await self._session.get(ProjectOrmModel, project_id)
        return mappers.project_to_domain(row) if row and row.deleted_at is None else None

    async def list_for_workspace(self, workspace_id: EntityId, *, include_archived: bool = False) -> list[Project]:
        stmt = select(ProjectOrmModel).where(
            ProjectOrmModel.workspace_id == workspace_id, ProjectOrmModel.deleted_at.is_(None)
        )
        if not include_archived:
            stmt = stmt.where(ProjectOrmModel.status != "archived")
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.project_to_domain(r) for r in rows]

    async def add(self, project: Project) -> None:
        self._session.add(mappers.project_to_orm(project))

    async def update(self, project: Project) -> None:
        row = await self._session.get(ProjectOrmModel, project.id)
        if row is None:
            raise ValueError(f"Project {project.id} not found for update")
        if row.version != project.version:
            raise ConcurrencyConflictError("Project", project.id)
        mappers.project_to_orm(project, row)
        row.version = project.version + 1
        project.version += 1


class SqlAlchemyProjectMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, project_id: EntityId, user_id: UserId) -> ProjectMembership | None:
        stmt = select(ProjectMembershipOrmModel).where(
            ProjectMembershipOrmModel.project_id == project_id, ProjectMembershipOrmModel.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.project_membership_to_domain(row) if row else None

    async def list_for_project(self, project_id: EntityId) -> list[ProjectMembership]:
        stmt = select(ProjectMembershipOrmModel).where(ProjectMembershipOrmModel.project_id == project_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.project_membership_to_domain(r) for r in rows]

    async def list_for_user(self, user_id: UserId) -> list[ProjectMembership]:
        stmt = select(ProjectMembershipOrmModel).where(ProjectMembershipOrmModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.project_membership_to_domain(r) for r in rows]

    async def count_owners(self, project_id: EntityId) -> int:
        stmt = select(func.count()).select_from(ProjectMembershipOrmModel).where(
            ProjectMembershipOrmModel.project_id == project_id,
            ProjectMembershipOrmModel.role == ProjectRole.OWNER.value,
            ProjectMembershipOrmModel.status == "active",
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def add(self, membership: ProjectMembership) -> None:
        self._session.add(mappers.project_membership_to_orm(membership))

    async def update(self, membership: ProjectMembership) -> None:
        row = await self._session.get(ProjectMembershipOrmModel, membership.id)
        if row is None:
            raise ValueError(f"ProjectMembership {membership.id} not found for update")
        mappers.project_membership_to_orm(membership, row)

    async def delete(self, membership_id: EntityId) -> None:
        row = await self._session.get(ProjectMembershipOrmModel, membership_id)
        if row is not None:
            await self._session.delete(row)


class SqlAlchemyProjectTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, template_id: EntityId) -> ProjectTemplate | None:
        row = await self._session.get(ProjectTemplateOrmModel, template_id)
        return mappers.project_template_to_domain(row) if row and row.deleted_at is None else None

    async def list_for_org(self, org_id: OrgId) -> list[ProjectTemplate]:
        stmt = select(ProjectTemplateOrmModel).where(
            ProjectTemplateOrmModel.org_id == org_id, ProjectTemplateOrmModel.deleted_at.is_(None)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.project_template_to_domain(r) for r in rows]

    async def get_default(self, org_id: OrgId) -> ProjectTemplate | None:
        stmt = select(ProjectTemplateOrmModel).where(
            ProjectTemplateOrmModel.org_id == org_id, ProjectTemplateOrmModel.is_default.is_(True),
            ProjectTemplateOrmModel.deleted_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.project_template_to_domain(row) if row else None

    async def add(self, template: ProjectTemplate) -> None:
        self._session.add(mappers.project_template_to_orm(template))

    async def update(self, template: ProjectTemplate) -> None:
        row = await self._session.get(ProjectTemplateOrmModel, template.id)
        if row is None:
            raise ValueError(f"ProjectTemplate {template.id} not found for update")
        if row.version != template.version:
            raise ConcurrencyConflictError("ProjectTemplate", template.id)
        mappers.project_template_to_orm(template, row)
        row.version = template.version + 1
        template.version += 1

    async def delete(self, template_id: EntityId) -> None:
        from datetime import UTC, datetime

        row = await self._session.get(ProjectTemplateOrmModel, template_id)
        if row is not None:
            row.deleted_at = datetime.now(UTC)


class SqlAlchemyProjectsAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: ProjectsAuditLogRecord) -> None:
        self._session.add(mappers.audit_log_to_orm(record))

    async def list_for_org(
        self, org_id: OrgId, *, category: ProjectsAuditEventCategory | None = None, limit: int = 50
    ) -> list[ProjectsAuditLogRecord]:
        stmt = select(ProjectsAuditLogOrmModel).where(ProjectsAuditLogOrmModel.org_id == org_id)
        if category is not None:
            stmt = stmt.where(ProjectsAuditLogOrmModel.category == category.value)
        stmt = stmt.order_by(ProjectsAuditLogOrmModel.occurred_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.audit_log_to_domain(r) for r in rows]
