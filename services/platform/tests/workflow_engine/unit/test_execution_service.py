import pytest

from app.workflow_engine.application.action_execution import ActionExecutor
from app.workflow_engine.application.execution_service import WorkflowExecutionService
from app.workflow_engine.application.ports import ProjectMemberSummary, ProjectSummary, TaskStatusRejectedError, TaskSummary
from app.workflow_engine.application.rule_evaluation import RuleEvaluator
from app.workflow_engine.application.state_management import WorkflowStateService
from app.workflow_engine.application.transition_management import WorkflowTransitionService
from app.workflow_engine.application.workflow_management import WorkflowService
from app.workflow_engine.domain.entities import ActionType, ConditionOperator, ConditionType, RuleType
from app.workflow_engine.domain.exceptions import (
    ApprovalRequiredError,
    ChecklistIncompleteError,
    ConditionsNotMetError,
    InvalidTransitionError,
    TaskAlreadyEnrolledError,
    TaskNotEnrolledError,
    TransitionDisabledError,
    WorkflowHasNoInitialStateError,
)
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.workflow_engine.unit.fakes import (
    AllowAllPermissionChecker,
    FakeBoardsContext,
    FakeProjectContext,
    FakeTasksContext,
    FakeUserDirectory,
    FakeWebhookExecutor,
    FakeWorkflowEngineUnitOfWork,
)


@pytest.fixture
def context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    actor_id = UserId(new_uuid7())
    task_id = EntityId(new_uuid7())
    uow = FakeWorkflowEngineUnitOfWork()
    project_context = FakeProjectContext(
        project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active"),
        members=[ProjectMemberSummary(user_id=actor_id, role="owner", status="active")],
    )
    tasks_context = FakeTasksContext(
        tasks=[TaskSummary(id=task_id, project_id=project_id, org_id=org_id, title="Demo", status="todo", priority="high", assignee_ids=(), label_ids=())]
    )
    boards_context = FakeBoardsContext()
    dispatcher = EventDispatcher()
    permission_checker = AllowAllPermissionChecker()

    workflow_service = WorkflowService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    state_service = WorkflowStateService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)
    transition_service = WorkflowTransitionService(uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context)

    rule_evaluator = RuleEvaluator(permission_checker=permission_checker, project_context=project_context)
    action_executor = ActionExecutor(
        tasks_context=tasks_context, notification_dispatcher=None, user_directory=FakeUserDirectory(),
        webhook_executor=FakeWebhookExecutor(),
    )
    execution_service = WorkflowExecutionService(
        uow_factory=lambda: uow, dispatcher=dispatcher, permission_checker=permission_checker, project_context=project_context,
        tasks_context=tasks_context, boards_context=boards_context, rule_evaluator=rule_evaluator, action_executor=action_executor,
    )
    return {
        "uow": uow, "workflow_service": workflow_service, "state_service": state_service,
        "transition_service": transition_service, "execution_service": execution_service, "tasks_context": tasks_context,
        "project_id": project_id, "org_id": org_id, "actor_id": actor_id, "task_id": task_id,
    }


async def _make_simple_workflow(ctx):
    workflow = await ctx["workflow_service"].create_workflow(project_id=ctx["project_id"], org_id=ctx["org_id"], actor_user_id=ctx["actor_id"], name="Demo")
    todo = await ctx["state_service"].create_state(workflow_id=workflow.id, actor_user_id=ctx["actor_id"], name="Todo", is_initial=True)
    done = await ctx["state_service"].create_state(workflow_id=workflow.id, actor_user_id=ctx["actor_id"], name="Done", is_final=True, mapped_task_status="done")
    transition = await ctx["transition_service"].create_transition(workflow_id=workflow.id, actor_user_id=ctx["actor_id"], name="Complete", from_state_id=todo.id, to_state_id=done.id)
    return workflow, todo, done, transition


@pytest.mark.asyncio
async def test_enroll_task_starts_at_initial_state(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)

    task_state = await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    assert task_state.current_state_id == todo.id


@pytest.mark.asyncio
async def test_enroll_task_twice_raises(context) -> None:
    workflow, *_ = await _make_simple_workflow(context)
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    with pytest.raises(TaskAlreadyEnrolledError):
        await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_enroll_task_without_initial_state_raises(context) -> None:
    workflow = await context["workflow_service"].create_workflow(project_id=context["project_id"], org_id=context["org_id"], actor_user_id=context["actor_id"], name="No Initial")

    with pytest.raises(WorkflowHasNoInitialStateError):
        await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_execute_transition_moves_state_and_syncs_mapped_task_status(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    result = await context["execution_service"].execute_transition(
        workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"], reason="ready",
    )

    assert result.current_state_id == done.id
    assert (context["task_id"], "done") in context["tasks_context"].status_changes

    history = await context["execution_service"].list_execution_history(workflow_id=workflow.id, task_id=context["task_id"])
    assert len(history) == 1
    assert history[0].from_state_id == todo.id
    assert history[0].to_state_id == done.id
    assert history[0].reason == "ready"


@pytest.mark.asyncio
async def test_execute_transition_without_enrollment_raises(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)

    with pytest.raises(TaskNotEnrolledError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_execute_disabled_transition_raises(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])
    await context["transition_service"].disable_transition(transition_id=transition.id, actor_user_id=context["actor_id"])

    with pytest.raises(TransitionDisabledError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_execute_transition_from_wrong_state_raises(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    other = await context["state_service"].create_state(workflow_id=workflow.id, actor_user_id=context["actor_id"], name="Other")
    wrong_transition = await context["transition_service"].create_transition(workflow_id=workflow.id, actor_user_id=context["actor_id"], name="From Other", from_state_id=other.id, to_state_id=done.id)
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    with pytest.raises(InvalidTransitionError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=wrong_transition.id, actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_execute_transition_rejected_by_tasks_context_propagates(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    context["tasks_context"]._reject_statuses.add("done")
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    with pytest.raises(TaskStatusRejectedError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_conditions_block_transition_when_unmet(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["transition_service"].add_condition(transition_id=transition.id, actor_user_id=context["actor_id"], condition_type=ConditionType.PRIORITY, operator=ConditionOperator.EQUALS, value="low")
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    with pytest.raises(ConditionsNotMetError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])


@pytest.mark.asyncio
async def test_conditions_allow_transition_when_met(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["transition_service"].add_condition(transition_id=transition.id, actor_user_id=context["actor_id"], condition_type=ConditionType.PRIORITY, operator=ConditionOperator.EQUALS, value="high")
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    result = await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])
    assert result.current_state_id == done.id


@pytest.mark.asyncio
async def test_required_approval_rule_blocks_until_approved(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["transition_service"].add_rule(transition_id=transition.id, actor_user_id=context["actor_id"], rule_type=RuleType.REQUIRED_APPROVAL, config={})
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    with pytest.raises(ApprovalRequiredError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])

    approval = await context["execution_service"].request_approval(transition_id=transition.id, task_id=context["task_id"], actor_user_id=context["actor_id"])
    await context["execution_service"].decide_approval(approval_id=approval.id, actor_user_id=context["actor_id"], approved=True)

    result = await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])
    assert result.current_state_id == done.id


@pytest.mark.asyncio
async def test_required_checklist_completion_blocks_until_all_items_done(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["transition_service"].add_rule(transition_id=transition.id, actor_user_id=context["actor_id"], rule_type=RuleType.REQUIRED_CHECKLIST_COMPLETION, config={})
    item = await context["transition_service"].add_checklist_item(transition_id=transition.id, actor_user_id=context["actor_id"], label="Confirm tests pass")
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    with pytest.raises(ChecklistIncompleteError):
        await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])

    await context["execution_service"].complete_checklist_item(item_id=item.id, task_id=context["task_id"], actor_user_id=context["actor_id"])
    result = await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])
    assert result.current_state_id == done.id


@pytest.mark.asyncio
async def test_automatic_transition_fires_after_manual_transition(context) -> None:
    """Automatic Transitions (submodule 7): from Done, an automatic
    transition to Archived should fire on its own once Done is reached,
    with no separate manual call."""
    workflow, todo, done, transition = await _make_simple_workflow(context)
    archived = await context["state_service"].create_state(workflow_id=workflow.id, actor_user_id=context["actor_id"], name="Archived")
    await context["transition_service"].create_transition(
        workflow_id=workflow.id, actor_user_id=context["actor_id"], name="Auto Archive", from_state_id=done.id,
        to_state_id=archived.id, is_automatic=True,
    )
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    result = await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])

    assert result.current_state_id == archived.id
    history = await context["execution_service"].list_execution_history(workflow_id=workflow.id, task_id=context["task_id"])
    assert len(history) == 2
    assert history[1].reason == "automatic"


@pytest.mark.asyncio
async def test_immediate_action_writes_activity_entry(context) -> None:
    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["transition_service"].add_action(transition_id=transition.id, actor_user_id=context["actor_id"], action_type=ActionType.CREATE_COMMENT, config={"body": "Marked complete"})
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])

    entries = await context["uow"].activity_entries.list_for_task(workflow.id, context["task_id"])
    assert len(entries) == 1
    assert entries[0].body == "Marked complete"


@pytest.mark.asyncio
async def test_delayed_action_is_scheduled_not_executed_immediately(context) -> None:
    from app.workflow_engine.domain.entities import ActionTriggerMode

    workflow, todo, done, transition = await _make_simple_workflow(context)
    await context["transition_service"].add_action(
        transition_id=transition.id, actor_user_id=context["actor_id"], action_type=ActionType.CREATE_COMMENT,
        config={"body": "Later"}, trigger_mode=ActionTriggerMode.DELAYED, delay_seconds=3600,
    )
    await context["execution_service"].enroll_task(workflow_id=workflow.id, task_id=context["task_id"], actor_user_id=context["actor_id"])

    await context["execution_service"].execute_transition(workflow_id=workflow.id, task_id=context["task_id"], transition_id=transition.id, actor_user_id=context["actor_id"])

    entries = await context["uow"].activity_entries.list_for_task(workflow.id, context["task_id"])
    assert entries == []
    pending = list(context["uow"].pending_actions.pending.values())
    assert len(pending) == 1
    assert pending[0].status.value == "pending"
    assert pending[0].actor_user_id == context["actor_id"]
