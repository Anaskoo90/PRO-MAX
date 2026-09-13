import pytest
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.tasks.application.ports import ProjectSummary
from app.tasks.application.workflow_management import WorkflowService
from app.tasks.domain.exceptions import ProjectNotAccessibleError

from tests.tasks.unit.fakes import (
    AllowAllPermissionChecker,
    FakeProjectContext,
    FakeTasksUnitOfWork,
)


def _make_context() -> tuple[
    FakeTasksUnitOfWork,
    FakeProjectContext,
    EntityId,
    OrgId,
    UserId,
]:
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    project_context = FakeProjectContext(
        project=ProjectSummary(
            id=project_id,
            org_id=org_id,
            workspace_id=new_uuid7(),
            status="active",
        )
    )
    return (
        FakeTasksUnitOfWork(),
        project_context,
        project_id,
        org_id,
        UserId(new_uuid7()),
    )


def _make_service(
    uow: FakeTasksUnitOfWork,
    project_context: FakeProjectContext,
) -> WorkflowService:
    return WorkflowService(
        uow_factory=lambda: uow,
        dispatcher=EventDispatcher(),
        permission_checker=AllowAllPermissionChecker(),
        project_context=project_context,
    )


@pytest.mark.asyncio
async def test_create_workflow_denies_cross_tenant_project_access() -> None:
    uow, project_context, project_id, _actual_org_id, actor_id = _make_context()
    service = _make_service(uow, project_context)

    with pytest.raises(ProjectNotAccessibleError):
        await service.create_or_replace_workflow(
            project_id=project_id,
            org_id=OrgId(new_uuid7()),
            actor_user_id=actor_id,
            name="Tenant workflow",
            statuses=["todo", "done"],
            transitions={"todo": ["done"]},
        )

    assert uow.workflow_definitions.workflows == {}
    assert uow.outbox.events == []


@pytest.mark.asyncio
async def test_create_workflow_allows_same_tenant_and_uses_resource_org() -> None:
    uow, project_context, project_id, actual_org_id, actor_id = _make_context()
    service = _make_service(uow, project_context)

    workflow = await service.create_or_replace_workflow(
        project_id=project_id,
        org_id=actual_org_id,
        actor_user_id=actor_id,
        name="Tenant workflow",
        statuses=["todo", "done"],
        transitions={"todo": ["done"]},
    )

    assert workflow.project_id == project_id
    assert workflow.name == "Tenant workflow"
    assert len(uow.outbox.events) == 1
    assert uow.outbox.events[0].org_id == actual_org_id
    assert (
        uow.outbox.events[0].payload["event_type"]
        == "tasks.workflow_definition_created"
    )
