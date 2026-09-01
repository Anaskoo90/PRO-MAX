import pytest

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.projects.application.template_management import ProjectTemplateService
from app.projects.application.workspace_management import WorkspaceService
from app.projects.domain.entities import ProjectTemplate
from app.projects.domain.exceptions import ProjectTemplateNotFoundError, WorkspaceNotFoundError
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
