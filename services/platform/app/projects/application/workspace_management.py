"""Workspace submodule: workspace CRUD, members, settings, permissions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.projects.application.authorization_helpers import WorkspaceAuthorization
from app.projects.application.dtos import WorkspaceDTO, WorkspaceMembershipDTO
from app.projects.application.ports import OrgPermissionCheckerPort
from app.projects.domain.audit import ProjectsAuditEventCategory, ProjectsAuditLogRecord
from app.projects.domain.entities import Workspace, WorkspaceMembership, WorkspaceRole
from app.projects.domain.events import WorkspaceMemberAdded, WorkspaceMemberRemoved
from app.projects.domain.exceptions import (
    InsufficientProjectRoleError,
    WorkspaceMembershipAlreadyExistsError,
    WorkspaceMembershipNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceSlugTakenError,
)


def _to_dto(workspace: Workspace) -> WorkspaceDTO:
    return WorkspaceDTO(
        id=workspace.id, org_id=workspace.org_id, name=workspace.name, slug=workspace.slug,
        description=workspace.description, status=workspace.status.value, settings=workspace.settings,
    )


def _membership_to_dto(m: WorkspaceMembership) -> WorkspaceMembershipDTO:
    return WorkspaceMembershipDTO(id=m.id, workspace_id=m.workspace_id, user_id=m.user_id, role=m.role.value, joined_at=m.joined_at)


class WorkspaceService:
    def __init__(
        self,
        *,
        uow_factory,
        dispatcher: EventDispatcher,
        permission_checker: OrgPermissionCheckerPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = WorkspaceAuthorization(permission_checker=permission_checker)
        self._permission_checker = permission_checker

    async def create_workspace(
        self, *, org_id: OrgId, actor_user_id: UserId, name: str, slug: str, description: str = ""
    ) -> WorkspaceDTO:
        if not await self._permission_checker.has_permission(
            user_id=actor_user_id, org_id=org_id, resource="workspace", action="create"
        ):
            raise InsufficientProjectRoleError(("org:workspace:create",))

        async with self._uow_factory() as uow:
            if await uow.workspaces.get_by_slug(org_id, slug) is not None:
                raise WorkspaceSlugTakenError(slug)

            workspace = Workspace.create(org_id=org_id, name=name, slug=slug, description=description)
            await uow.workspaces.add(workspace)
            await uow.workspace_memberships.add(
                WorkspaceMembership.create(workspace_id=workspace.id, user_id=actor_user_id, role=WorkspaceRole.OWNER)
            )
            events = workspace.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=org_id, category=ProjectsAuditEventCategory.WORKSPACE_CHANGE, action="workspace_created",
                    actor_user_id=actor_user_id, resource_type="workspace", resource_id=str(workspace.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workspace)

    async def get(self, *, workspace_id: EntityId) -> WorkspaceDTO:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            return _to_dto(workspace)

    async def list_for_org(self, *, org_id: OrgId) -> list[WorkspaceDTO]:
        async with self._uow_factory() as uow:
            workspaces = await uow.workspaces.list_for_org(org_id)
            return [_to_dto(w) for w in workspaces]

    async def update(
        self, *, workspace_id: EntityId, actor_user_id: UserId, name: str | None, description: str | None
    ) -> WorkspaceDTO:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            if not await self._authorization.can_manage(uow=uow, workspace_id=workspace_id, org_id=workspace.org_id, user_id=actor_user_id):
                raise InsufficientProjectRoleError(("owner", "admin"))

            if name is not None:
                workspace.rename(name)
            if description is not None:
                workspace.update_description(description)
            await uow.workspaces.update(workspace)
            events = workspace.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workspace)

    async def update_settings(self, *, workspace_id: EntityId, actor_user_id: UserId, patch: dict[str, Any]) -> WorkspaceDTO:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            if not await self._authorization.can_manage(uow=uow, workspace_id=workspace_id, org_id=workspace.org_id, user_id=actor_user_id):
                raise InsufficientProjectRoleError(("owner", "admin"))

            workspace.update_settings(patch)
            await uow.workspaces.update(workspace)
            events = workspace.pull_domain_events()
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workspace)

    async def _set_archived(self, *, workspace_id: EntityId, actor_user_id: UserId, archive: bool) -> WorkspaceDTO:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            if not await self._authorization.can_manage(uow=uow, workspace_id=workspace_id, org_id=workspace.org_id, user_id=actor_user_id):
                raise InsufficientProjectRoleError(("owner", "admin"))

            workspace.archive() if archive else workspace.reactivate()
            await uow.workspaces.update(workspace)
            events = workspace.pull_domain_events()
            await uow.audit_logs.add(
                ProjectsAuditLogRecord.create(
                    org_id=workspace.org_id, category=ProjectsAuditEventCategory.WORKSPACE_CHANGE,
                    action="workspace_archived" if archive else "workspace_reactivated",
                    actor_user_id=actor_user_id, resource_type="workspace", resource_id=str(workspace.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(workspace)

    async def archive(self, *, workspace_id: EntityId, actor_user_id: UserId) -> WorkspaceDTO:
        return await self._set_archived(workspace_id=workspace_id, actor_user_id=actor_user_id, archive=True)

    async def reactivate(self, *, workspace_id: EntityId, actor_user_id: UserId) -> WorkspaceDTO:
        return await self._set_archived(workspace_id=workspace_id, actor_user_id=actor_user_id, archive=False)

    async def add_member(
        self, *, workspace_id: EntityId, actor_user_id: UserId, target_user_id: UserId, role: WorkspaceRole
    ) -> WorkspaceMembershipDTO:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            if not await self._authorization.can_manage(uow=uow, workspace_id=workspace_id, org_id=workspace.org_id, user_id=actor_user_id):
                raise InsufficientProjectRoleError(("owner", "admin"))
            if await uow.workspace_memberships.get(workspace_id, target_user_id) is not None:
                raise WorkspaceMembershipAlreadyExistsError()

            membership = WorkspaceMembership.create(workspace_id=workspace_id, user_id=target_user_id, role=role)
            await uow.workspace_memberships.add(membership)
            await uow.commit()
            # WorkspaceMembership is a plain join entity (no EventRecordingMixin,
            # same convention as Identity's TeamMembership) — the event is
            # constructed and dispatched here at the application layer instead.
            await self._dispatcher.dispatch(
                WorkspaceMemberAdded(aggregate_id=workspace_id, user_id=target_user_id, role=role.value)
            )
            return _membership_to_dto(membership)

    async def remove_member(self, *, workspace_id: EntityId, actor_user_id: UserId, target_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get_by_id(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)
            if not await self._authorization.can_manage(uow=uow, workspace_id=workspace_id, org_id=workspace.org_id, user_id=actor_user_id):
                raise InsufficientProjectRoleError(("owner", "admin"))

            membership = await uow.workspace_memberships.get(workspace_id, target_user_id)
            if membership is None:
                raise WorkspaceMembershipNotFoundError(workspace_id, target_user_id)
            await uow.workspace_memberships.delete(membership.id)
            await uow.commit()
            await self._dispatcher.dispatch(WorkspaceMemberRemoved(aggregate_id=workspace_id, user_id=target_user_id))

    async def list_members(self, *, workspace_id: EntityId) -> list[WorkspaceMembershipDTO]:
        async with self._uow_factory() as uow:
            memberships = await uow.workspace_memberships.list_for_workspace(workspace_id)
            return [_membership_to_dto(m) for m in memberships]

    async def can_manage(self, *, workspace_id: EntityId, org_id: OrgId, user_id: UserId) -> bool:
        """Workspace Permissions: a direct capability query, distinct from
        the enforcement path (`update`/`archive`/... raise instead), for
        callers (e.g. the frontend) that need to know in advance whether to
        render management controls at all."""
        async with self._uow_factory() as uow:
            return await self._authorization.can_manage(uow=uow, workspace_id=workspace_id, org_id=org_id, user_id=user_id)
