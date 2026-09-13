import pytest

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.projects.application.template_management import ProjectTemplateService
from app.projects.application.project_management import ProjectService
from app.projects.application.workspace_management import WorkspaceService
from app.projects.domain.entities import Project, ProjectTemplate, Workspace
from app.projects.domain.exceptions import ProjectNotFoundError, ProjectTemplateNotFoundError, WorkspaceNotFoundError
from tests.projects.unit.fakes import AllowAllPermissionChecker, FakeProjectsUnitOfWork


@pytest.mark.asyncio
async def test_org_a_cannot_read_org_b_workspace_or_memberships() -> None:
    uow = FakeProjectsUnitOfWork()
    org_a = OrgId(new_uuid7())
    org_b = OrgId(new_uuid7())
    service = WorkspaceService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker()
    )
    workspace_b = await service.create_workspace(
        org_id=org_b, actor_user_id=UserId(new_uuid7()), name="Organization B", slug="organization-b"
    )

    with pytest.raises(WorkspaceNotFoundError):
        await service.get_for_org(org_id=org_a, workspace_id=workspace_b.id)
    with pytest.raises(WorkspaceNotFoundError):
        await service.list_members_for_org(org_id=org_a, workspace_id=workspace_b.id)


@pytest.mark.asyncio
async def test_org_a_cannot_export_org_b_template() -> None:
    uow = FakeProjectsUnitOfWork()
    org_a = OrgId(new_uuid7())
    template_b = ProjectTemplate.create(org_id=OrgId(new_uuid7()), name="Organization B template")
    await uow.project_templates.add(template_b)
    service = ProjectTemplateService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker()
    )

    with pytest.raises(ProjectTemplateNotFoundError):
        await service.export_template_for_org(org_id=org_a, template_id=template_b.id)


@pytest.mark.asyncio
async def test_project_read_denies_cross_tenant_and_allows_same_tenant() -> None:
    uow = FakeProjectsUnitOfWork()
    org_id = OrgId(new_uuid7())
    user_id = UserId(new_uuid7())
    workspace = Workspace.create(org_id=org_id, name="Eng", slug="eng")
    project = Project.create(workspace_id=workspace.id, org_id=org_id, name="Tenant project")
    await uow.workspaces.add(workspace)
    await uow.projects.add(project)
    service = ProjectService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(), permission_checker=AllowAllPermissionChecker()
    )

    with pytest.raises(ProjectNotFoundError):
        await service.get_for_actor(
            project_id=project.id, org_id=OrgId(new_uuid7()), user_id=user_id
        )

    result = await service.get_for_actor(project_id=project.id, org_id=org_id, user_id=user_id)
    assert result.id == project.id
    listed = await service.list_for_workspace_for_actor(
        workspace_id=workspace.id, org_id=org_id, user_id=user_id
    )
    assert [item.id for item in listed] == [project.id]
