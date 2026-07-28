import pytest

from app.workflow_engine.application.ports import ProjectMemberSummary, ProjectSummary
from app.workflow_engine.application.state_management import WorkflowStateService
from app.workflow_engine.application.workflow_management import WorkflowService
from app.workflow_engine.domain.exceptions import StateNameAlreadyExistsError
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.workflow_engine.unit.fakes import AllowAllPermissionChecker, FakeProjectContext, FakeWorkflowEngineUnitOfWork


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
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    workflow_service = WorkflowService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    state_service = WorkflowStateService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    return workflow_service, state_service, project_id, org_id, actor_id


@pytest.mark.asyncio
async def test_create_state_computes_incrementing_positions(context) -> None:
    workflow_service, state_service, project_id, org_id, actor_id = context
    workflow = await workflow_service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")

    todo = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Todo")
    done = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Done")

    assert todo.position < done.position


@pytest.mark.asyncio
async def test_duplicate_state_name_on_same_workflow_rejected(context) -> None:
    workflow_service, state_service, project_id, org_id, actor_id = context
    workflow = await workflow_service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Todo")

    with pytest.raises(StateNameAlreadyExistsError):
        await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Todo")


@pytest.mark.asyncio
async def test_only_one_state_can_be_initial(context) -> None:
    workflow_service, state_service, project_id, org_id, actor_id = context
    workflow = await workflow_service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    first = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="New", is_initial=True)
    second = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Triaged", is_initial=True)

    states = await state_service.list_for_workflow(workflow_id=workflow.id)
    initial_states = [s for s in states if s.is_initial]

    assert len(initial_states) == 1
    assert initial_states[0].id == second.id
    assert first.id != second.id


@pytest.mark.asyncio
async def test_set_initial_moves_the_flag(context) -> None:
    workflow_service, state_service, project_id, org_id, actor_id = context
    workflow = await workflow_service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    first = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="New", is_initial=True)
    second = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Triaged")

    await state_service.set_initial(state_id=second.id, actor_user_id=actor_id)

    states = await state_service.list_for_workflow(workflow_id=workflow.id)
    by_id = {s.id: s for s in states}
    assert by_id[first.id].is_initial is False
    assert by_id[second.id].is_initial is True


@pytest.mark.asyncio
async def test_delete_state_referenced_by_transition_is_rejected() -> None:
    from app.workflow_engine.application.transition_management import WorkflowTransitionService
    from app.workflow_engine.domain.exceptions import StateInUseError

    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    uow = FakeWorkflowEngineUnitOfWork()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()
    workflow_service = WorkflowService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    state_service = WorkflowStateService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    transition_service = WorkflowTransitionService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)

    workflow = await workflow_service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    from_state = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Todo")
    to_state = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Done")
    await transition_service.create_transition(workflow_id=workflow.id, actor_user_id=actor_id, name="Complete", from_state_id=from_state.id, to_state_id=to_state.id)

    with pytest.raises(StateInUseError):
        await state_service.delete_state(state_id=from_state.id, actor_user_id=actor_id)
