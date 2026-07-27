"""
Project Aggregate submodule: create, update, archive, delete, status,
visibility, metadata, settings.

Creation applies a template's defaults (visibility/metadata/settings) when
one is given — explicit arguments always win over template defaults,
matching the general "explicit beats implicit" precedent already used
across the platform's config-merging code (e.g. PlatformSettings).
"""

from __future__ import annotations

from typing import Any

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.projects.application.authorization_helpers import ProjectAuthorization, WorkspaceAuthorization
from app.projects.application.dtos import ProjectDTO
from app.projects.application.ports import OrgPermissionCheckerPort
from app.projects.domain.audit import ProjectsAuditEventCategory, ProjectsAuditLogRecord
from app.projects.domain.entities import (
    MembershipStatus,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    ProjectVisibility,
)
from app.projects.domain.exceptions import (
    InsufficientProjectRoleError,
    ProjectNotFoundError,
    WorkspaceNotFoundError,
)


def _to_dto(project: Project) -> ProjectDTO:
    return ProjectDTO(
        id=project.id, workspace_id=project.workspace_id, org_id=project.org_id, name=project.name,
        description=project.description, status=project.status.value, visibility=project.visibility.value,
        metadata=project.metadata, settings=project.settings, template_id=project.template_id,
        archived_at=project.archived_at,
    )


class ProjectService:
    def __init__(
        self,
        *,
        uow_factory,
        dispatcher: EventDispatcher,
        permission_checker: OrgPermissionCheckerPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._workspace_authorization = WorkspaceAuthorization(permission_checker=permission_checker)
        self._project_authorization = ProjectAuthorization(permission_checker=permission_checker)

    async def create_project(
        self,
        *,
        workspace_id: EntityId,
        actor_user_id: UserId,
        name: str,
        description: str = "",
        visibility: ProjectVisibility | None = None,
        metadata: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        template_id: EntityId | None = None,
    ) -> ProjectDTO:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            workspace.assert_active()
            if not await self._workspace_authorization.can_create_projects(
                uow=uow, workspace_id=workspace_id, org_id=workspace.org_id, user_id=actor_user_id
            ):
                raise InsufficientProjectRoleError(("workspace:owner", "workspace:admin", "workspace:member"))

            effective_visibility = visibility
            effective_metadata = dict(metadata or {})
            effective_settings = dict(settings or {})
            if template_id is not None:
                template = await uow.project_templates.get_by_id(template_id)
                if template is not None:
                    effective_visibility = effective_visibility or template.default_visibility
                    effective_metadata = {**template.default_metadata, **effective_metadata}
                    effective_settings = {**template.default_settings, **effective_settings}

            project = Project.create(
                workspace_id=workspace_id, org_id=workspace.org_id, name=name, description=description,
                visibility=effective_visibility or ProjectVisibility.WORKSPACE, metadata=effective_metadata,
                settings=effective_settings, template_id=template_id,
            )
            await uow.projects.add(project)
            await uow.project_memberships.add(
                ProjectMembership.add_directly(project_id=project.id, user_id=actor_user_id, role=ProjectRole.OWNER)
            )
            events = project.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=workspace.org_id, category=ProjectsAuditEventCategory.PROJECT_CHANGE, action="project_created",
                    actor_user_id=actor_user_id, resource_type="project", resource_id=str(project.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def get(self, *, project_id: EntityId) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await uow.projects.get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError(project_id)
            return _to_dto(project)

    async def list_for_workspace(self, *, workspace_id: EntityId, include_archived: bool = False) -> list[ProjectDTO]:
        async with self._uow_factory() as uow:
            projects = await uow.projects.list_for_workspace(workspace_id, include_archived=include_archived)
            return [_to_dto(p) for p in projects]

    async def _load_and_authorize(self, uow, *, project_id: EntityId, actor_user_id: UserId) -> Project:
        project = await uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        project.assert_not_deleted()
        await self._project_authorization.assert_can_manage(
            uow=uow, project_id=project_id, org_id=project.org_id, user_id=actor_user_id
        )
        return project

    async def update(
        self, *, project_id: EntityId, actor_user_id: UserId, name: str | None, description: str | None
    ) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.update(name=name, description=description)
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def update_metadata(self, *, project_id: EntityId, actor_user_id: UserId, patch: dict[str, Any]) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.update_metadata(patch)
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def update_settings(self, *, project_id: EntityId, actor_user_id: UserId, patch: dict[str, Any]) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.update_settings(patch)
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def change_status(self, *, project_id: EntityId, actor_user_id: UserId, status: ProjectStatus) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.change_status(status)
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def change_visibility(self, *, project_id: EntityId, actor_user_id: UserId, visibility: ProjectVisibility) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.change_visibility(visibility)
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def archive(self, *, project_id: EntityId, actor_user_id: UserId) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.archive()
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=project.org_id, category=ProjectsAuditEventCategory.PROJECT_CHANGE, action="project_archived",
                    actor_user_id=actor_user_id, resource_type="project", resource_id=str(project.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def unarchive(self, *, project_id: EntityId, actor_user_id: UserId) -> ProjectDTO:
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.unarchive()
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(project)

    async def delete(self, *, project_id: EntityId, actor_user_id: UserId) -> None:
        """Soft delete (deleted_at) — distinct from archive, per the
        platform-wide convention that entity tables never hard-delete."""
        async with self._uow_factory() as uow:
            project = await self._load_and_authorize(uow, project_id=project_id, actor_user_id=actor_user_id)
            project.mark_deleted()
            await uow.projects.update(project)
            events = project.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=project.org_id, category=ProjectsAuditEventCategory.PROJECT_CHANGE, action="project_deleted",
                    actor_user_id=actor_user_id, resource_type="project", resource_id=str(project.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
