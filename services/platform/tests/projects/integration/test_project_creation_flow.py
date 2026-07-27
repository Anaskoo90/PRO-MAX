"""
Exercises WorkspaceService.create_workspace + ProjectService.create_project
against the real database and real repository implementations — a mapper
or FK mistake here (e.g. the workspace_id -> projects.workspaces.id FK, or
the org_id cross-schema column) would only surface at this level, not in
the fakes-based unit tests.
"""

from __future__ import annotations

import pytest

from app.projects.application.project_management import ProjectService
from app.projects.application.workspace_management import WorkspaceService
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.projects.unit.fakes import AllowAllPermissionChecker

pytestmark = pytest.mark.asyncio


async def test_create_workspace_then_create_project_persists_both(uow) -> None:
    def uow_factory():
        return uow

    org_id = OrgId(new_uuid7())
    actor_id = UserId(new_uuid7())

    workspace_service = WorkspaceService(
        uow_factory=uow_factory, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker()
    )
    workspace = await workspace_service.create_workspace(
        org_id=org_id, actor_user_id=actor_id, name="Engineering", slug=f"eng-{new_uuid7().hex[:8]}"
    )
    await uow.session.flush()

    project_service = ProjectService(
        uow_factory=uow_factory, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker()
    )
    project = await project_service.create_project(workspace_id=workspace.id, actor_user_id=actor_id, name="New Project")
    await uow.session.flush()

    persisted_workspace = await uow.workspaces.get_by_id(workspace.id)
    persisted_project = await uow.projects.get_by_id(project.id)
    owner_membership = await uow.project_memberships.get(project.id, actor_id)

    assert persisted_workspace is not None
    assert persisted_project is not None
    assert persisted_project.workspace_id == persisted_workspace.id
    assert persisted_project.org_id == org_id
    assert owner_membership is not None
    assert owner_membership.role.value == "owner"
