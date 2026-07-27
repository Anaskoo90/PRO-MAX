import pytest

from app.projects.application.authorization_helpers import ProjectAuthorization, WorkspaceAuthorization
from app.projects.domain.entities import Project, ProjectMembership, ProjectRole, Workspace, WorkspaceMembership, WorkspaceRole
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.projects.unit.fakes import AllowAllPermissionChecker, DenyAllPermissionChecker, FakeProjectsUnitOfWork


@pytest.mark.asyncio
async def test_workspace_owner_can_manage_without_org_permission() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Eng", slug="eng")
    owner_id = UserId(new_uuid7())
    await uow.workspace_memberships.add(WorkspaceMembership.create(workspace_id=workspace.id, user_id=owner_id, role=WorkspaceRole.OWNER))

    auth = WorkspaceAuthorization(permission_checker=DenyAllPermissionChecker())
    assert await auth.can_manage(uow=uow, workspace_id=workspace.id, org_id=org_id, user_id=owner_id) is True


@pytest.mark.asyncio
async def test_non_member_without_org_permission_cannot_manage_workspace() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Eng", slug="eng")

    auth = WorkspaceAuthorization(permission_checker=DenyAllPermissionChecker())
    assert await auth.can_manage(uow=uow, workspace_id=workspace.id, org_id=org_id, user_id=UserId(new_uuid7())) is False


@pytest.mark.asyncio
async def test_org_admin_can_manage_workspace_without_being_a_member() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Eng", slug="eng")

    auth = WorkspaceAuthorization(permission_checker=AllowAllPermissionChecker())
    assert await auth.can_manage(uow=uow, workspace_id=workspace.id, org_id=org_id, user_id=UserId(new_uuid7())) is True


@pytest.mark.asyncio
async def test_workspace_viewer_cannot_create_projects() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Eng", slug="eng")
    viewer_id = UserId(new_uuid7())
    await uow.workspace_memberships.add(WorkspaceMembership.create(workspace_id=workspace.id, user_id=viewer_id, role=WorkspaceRole.VIEWER))

    auth = WorkspaceAuthorization(permission_checker=DenyAllPermissionChecker())
    assert await auth.can_create_projects(uow=uow, workspace_id=workspace.id, org_id=org_id, user_id=viewer_id) is False


@pytest.mark.asyncio
async def test_workspace_member_can_create_projects() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Eng", slug="eng")
    member_id = UserId(new_uuid7())
    await uow.workspace_memberships.add(WorkspaceMembership.create(workspace_id=workspace.id, user_id=member_id, role=WorkspaceRole.MEMBER))

    auth = WorkspaceAuthorization(permission_checker=DenyAllPermissionChecker())
    assert await auth.can_create_projects(uow=uow, workspace_id=workspace.id, org_id=org_id, user_id=member_id) is True


@pytest.mark.asyncio
async def test_project_contributor_cannot_manage_but_owner_can() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    project = Project.create(workspace_id=EntityId(new_uuid7()), org_id=org_id, name="Demo")
    owner_id = UserId(new_uuid7())
    contributor_id = UserId(new_uuid7())
    await uow.project_memberships.add(ProjectMembership.add_directly(project_id=project.id, user_id=owner_id, role=ProjectRole.OWNER))
    await uow.project_memberships.add(ProjectMembership.add_directly(project_id=project.id, user_id=contributor_id, role=ProjectRole.CONTRIBUTOR))

    auth = ProjectAuthorization(permission_checker=DenyAllPermissionChecker())
    assert await auth.can_manage(uow=uow, project_id=project.id, org_id=org_id, user_id=owner_id) is True
    assert await auth.can_manage(uow=uow, project_id=project.id, org_id=org_id, user_id=contributor_id) is False
