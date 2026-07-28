import pytest

from app.workflow_engine.application.ports import ProjectMemberSummary, ProjectSummary
from app.workflow_engine.application.workflow_management import WorkflowService
from app.workflow_engine.domain.exceptions import InsufficientWorkflowPermissionError, ProjectNotAccessibleError, WorkflowNotFoundError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.workflow_engine.unit.fakes import AllowAllPermissionChecker, DenyAllPermissionChecker, FakeProjectContext, FakeWorkflowEngineUnitOfWork


def _make_service(uow, project_context, permission_checker=None) -> WorkflowService:
    return WorkflowService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(),
        permission_checker=permission_checker or AllowAllPermissionChecker(), project_context=project_context,
    )


@pytest.fixture
def context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    uow = FakeWorkflowEngineUnitOfWork()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    return uow, project_context, project_id, org_id, actor_id


@pytest.mark.asyncio
async def test_create_workflow_succeeds_for_a_project_member(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)

    workflow = await service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Bug Triage")

    assert workflow.name == "Bug Triage"
    assert workflow.status == "active"


@pytest.mark.asyncio
async def test_create_workflow_rejects_mismatched_org_id(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    wrong_org_id = OrgId(new_uuid7())

    with pytest.raises(ProjectNotAccessibleError):
        await service.create_workflow(project_id=project_id, org_id=wrong_org_id, actor_user_id=actor_id, name="Demo")


@pytest.mark.asyncio
async def test_non_member_cannot_create_workflow(context) -> None:
    uow, project_context, project_id, org_id, _actor_id = context
    outsider_id = UserId(new_uuid7())
    service = _make_service(uow, project_context, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientWorkflowPermissionError):
        await service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=outsider_id, name="Demo")


@pytest.mark.asyncio
async def test_archive_restore_and_delete_round_trip(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    workflow = await service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    archived = await service.archive(workflow_id=workflow.id, actor_user_id=actor_id)
    assert archived.status == "archived"

    restored = await service.restore(workflow_id=workflow.id, actor_user_id=actor_id)
    assert restored.status == "active"

    await service.delete(workflow_id=workflow.id, actor_user_id=actor_id)
    with pytest.raises(WorkflowNotFoundError):
        await service.delete(workflow_id=workflow.id, actor_user_id=actor_id)


@pytest.mark.asyncio
async def test_update_changes_name_and_description(context) -> None:
    uow, project_context, project_id, org_id, actor_id = context
    service = _make_service(uow, project_context)
    workflow = await service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    updated = await service.update(workflow_id=workflow.id, actor_user_id=actor_id, description="Now with a description")

    assert updated.description == "Now with a description"
