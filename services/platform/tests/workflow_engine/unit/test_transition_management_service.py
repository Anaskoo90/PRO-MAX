import pytest

from app.workflow_engine.application.ports import ProjectMemberSummary, ProjectSummary
from app.workflow_engine.application.state_management import WorkflowStateService
from app.workflow_engine.application.transition_management import WorkflowTransitionService
from app.workflow_engine.application.workflow_management import WorkflowService
from app.workflow_engine.domain.entities import ActionType, ConditionOperator, ConditionType, RuleType
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
    transition_service = WorkflowTransitionService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    return workflow_service, state_service, transition_service, project_id, org_id, actor_id


async def _make_workflow_with_states(workflow_service, state_service, project_id, org_id, actor_id):
    workflow = await workflow_service.create_workflow(project_id=project_id, org_id=org_id, actor_user_id=actor_id, name="Demo")
    todo = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Todo", is_initial=True)
    done = await state_service.create_state(workflow_id=workflow.id, actor_user_id=actor_id, name="Done")
    return workflow, todo, done


@pytest.mark.asyncio
async def test_create_transition(context) -> None:
    workflow_service, state_service, transition_service, project_id, org_id, actor_id = context
    workflow, todo, done = await _make_workflow_with_states(workflow_service, state_service, project_id, org_id, actor_id)

    transition = await transition_service.create_transition(workflow_id=workflow.id, actor_user_id=actor_id, name="Complete", from_state_id=todo.id, to_state_id=done.id)

    assert transition.from_state_id == todo.id
    assert transition.to_state_id == done.id
    assert transition.enabled is True


@pytest.mark.asyncio
async def test_disable_then_enable_transition(context) -> None:
    workflow_service, state_service, transition_service, project_id, org_id, actor_id = context
    workflow, todo, done = await _make_workflow_with_states(workflow_service, state_service, project_id, org_id, actor_id)
    transition = await transition_service.create_transition(workflow_id=workflow.id, actor_user_id=actor_id, name="Complete", from_state_id=todo.id, to_state_id=done.id)

    disabled = await transition_service.disable_transition(transition_id=transition.id, actor_user_id=actor_id)
    assert disabled.enabled is False

    enabled = await transition_service.enable_transition(transition_id=transition.id, actor_user_id=actor_id)
    assert enabled.enabled is True


@pytest.mark.asyncio
async def test_add_rule_action_condition_and_checklist_item(context) -> None:
    workflow_service, state_service, transition_service, project_id, org_id, actor_id = context
    workflow, todo, done = await _make_workflow_with_states(workflow_service, state_service, project_id, org_id, actor_id)
    transition = await transition_service.create_transition(workflow_id=workflow.id, actor_user_id=actor_id, name="Complete", from_state_id=todo.id, to_state_id=done.id)

    rule = await transition_service.add_rule(transition_id=transition.id, actor_user_id=actor_id, rule_type=RuleType.REQUIRED_ROLE, config={"roles": ["owner"]})
    action = await transition_service.add_action(transition_id=transition.id, actor_user_id=actor_id, action_type=ActionType.CREATE_COMMENT, config={"body": "done"})
    condition = await transition_service.add_condition(transition_id=transition.id, actor_user_id=actor_id, condition_type=ConditionType.PRIORITY, operator=ConditionOperator.EQUALS, value="high")
    item = await transition_service.add_checklist_item(transition_id=transition.id, actor_user_id=actor_id, label="Confirm tests pass")

    assert (await transition_service.list_rules(transition_id=transition.id)) == [rule]
    assert (await transition_service.list_actions(transition_id=transition.id)) == [action]
    assert (await transition_service.list_conditions(transition_id=transition.id)) == [condition]
    assert (await transition_service.list_checklist_items(transition_id=transition.id)) == [item]


@pytest.mark.asyncio
async def test_delete_transition_cascades_its_rules_actions_conditions_and_checklist_items(context) -> None:
    workflow_service, state_service, transition_service, project_id, org_id, actor_id = context
    workflow, todo, done = await _make_workflow_with_states(workflow_service, state_service, project_id, org_id, actor_id)
    transition = await transition_service.create_transition(workflow_id=workflow.id, actor_user_id=actor_id, name="Complete", from_state_id=todo.id, to_state_id=done.id)
    await transition_service.add_rule(transition_id=transition.id, actor_user_id=actor_id, rule_type=RuleType.REQUIRED_ROLE, config={"roles": ["owner"]})
    await transition_service.add_action(transition_id=transition.id, actor_user_id=actor_id, action_type=ActionType.CREATE_COMMENT, config={"body": "done"})
    await transition_service.add_condition(transition_id=transition.id, actor_user_id=actor_id, condition_type=ConditionType.PRIORITY, operator=ConditionOperator.EQUALS, value="high")
    await transition_service.add_checklist_item(transition_id=transition.id, actor_user_id=actor_id, label="Confirm tests pass")

    await transition_service.delete_transition(transition_id=transition.id, actor_user_id=actor_id)

    assert await transition_service.list_rules(transition_id=transition.id) == []
    assert await transition_service.list_actions(transition_id=transition.id) == []
    assert await transition_service.list_conditions(transition_id=transition.id) == []
    assert await transition_service.list_checklist_items(transition_id=transition.id) == []
