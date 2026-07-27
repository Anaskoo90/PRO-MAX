import pytest

from app.projects.application.project_management import ProjectService
from app.projects.application.workspace_management import WorkspaceService
from app.projects.domain.entities import ProjectTemplate, ProjectVisibility, WorkspaceRole
from app.projects.domain.exceptions import InsufficientProjectRoleError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.projects.unit.fakes import AllowAllPermissionChecker, DenyAllPermissionChecker, FakeProjectsUnitOfWork


@pytest.mark.asyncio
async def test_create_project_applies_template_defaults() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    actor_id = UserId(new_uuid7())

    workspace_service = WorkspaceService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    workspace = await workspace_service.create_workspace(org_id=org_id, actor_user_id=actor_id, name="Eng", slug="eng")

    template = ProjectTemplate.create(
        org_id=org_id, name="Standard", default_visibility=ProjectVisibility.ORGANIZATION,
        default_metadata={"tag": "standard"}, default_settings={"kanban": True},
    )
    await uow.project_templates.add(template)

    project_service = ProjectService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    project = await project_service.create_project(
        workspace_id=workspace.id, actor_user_id=actor_id, name="New Project", template_id=template.id,
    )

    assert project.visibility == "organization"
    assert project.metadata == {"tag": "standard"}
    assert project.settings == {"kanban": True}


@pytest.mark.asyncio
async def test_create_project_explicit_values_override_template_defaults() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    actor_id = UserId(new_uuid7())

    workspace_service = WorkspaceService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    workspace = await workspace_service.create_workspace(org_id=org_id, actor_user_id=actor_id, name="Eng", slug="eng")

    template = ProjectTemplate.create(
        org_id=org_id, name="Standard", default_visibility=ProjectVisibility.ORGANIZATION,
        default_metadata={"tag": "standard"},
    )
    await uow.project_templates.add(template)

    project_service = ProjectService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    project = await project_service.create_project(
        workspace_id=workspace.id, actor_user_id=actor_id, name="New Project", template_id=template.id,
        visibility=ProjectVisibility.PRIVATE, metadata={"tag": "overridden"},
    )

    assert project.visibility == "private"
    assert project.metadata == {"tag": "overridden"}


@pytest.mark.asyncio
async def test_create_project_creator_becomes_active_owner() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    actor_id = UserId(new_uuid7())

    workspace_service = WorkspaceService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    workspace = await workspace_service.create_workspace(org_id=org_id, actor_user_id=actor_id, name="Eng", slug="eng")

    project_service = ProjectService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    project = await project_service.create_project(workspace_id=workspace.id, actor_user_id=actor_id, name="New Project")

    membership = await uow.project_memberships.get(project.id, actor_id)
    assert membership is not None
    assert membership.role.value == "owner"
    assert membership.status.value == "active"


@pytest.mark.asyncio
async def test_workspace_viewer_cannot_create_project_end_to_end() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    owner_id = UserId(new_uuid7())
    viewer_id = UserId(new_uuid7())

    workspace_service = WorkspaceService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker())
    workspace = await workspace_service.create_workspace(org_id=org_id, actor_user_id=owner_id, name="Eng", slug="eng")
    await workspace_service.add_member(workspace_id=workspace.id, actor_user_id=owner_id, target_user_id=viewer_id, role=WorkspaceRole.VIEWER)

    project_service = ProjectService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=DenyAllPermissionChecker())
    with pytest.raises(InsufficientProjectRoleError):
        await project_service.create_project(workspace_id=workspace.id, actor_user_id=viewer_id, name="Should Fail")
