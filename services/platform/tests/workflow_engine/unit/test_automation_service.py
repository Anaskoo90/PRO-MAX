from datetime import timedelta

import pytest

from app.workflow_engine.application.action_execution import ActionExecutor
from app.workflow_engine.application.automation_service import WorkflowAutomationService
from app.workflow_engine.application.ports import TaskSummary
from app.workflow_engine.domain.entities import ActionType, PendingAutomationAction, WorkflowAction
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from tests.workflow_engine.unit.fakes import FakeTasksContext, FakeUserDirectory, FakeWebhookExecutor, FakeWorkflowEngineUnitOfWork


@pytest.mark.asyncio
async def test_run_due_actions_executes_a_due_action_and_marks_it_executed() -> None:
    uow = FakeWorkflowEngineUnitOfWork()
    task_id = new_uuid7()
    actor_id = new_uuid7()
    tasks_context = FakeTasksContext(tasks=[TaskSummary(id=task_id, project_id=new_uuid7(), org_id=new_uuid7(), title="Demo", status="todo", priority="high", assignee_ids=(), label_ids=())])
    action_executor = ActionExecutor(tasks_context=tasks_context, notification_dispatcher=None, user_directory=FakeUserDirectory(), webhook_executor=FakeWebhookExecutor())

    from app.workflow_engine.domain.entities import WorkflowDefinition
    from app.platform_core.shared_kernel.types import EntityId, OrgId

    workflow = WorkflowDefinition.create(project_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), name="Demo")
    await uow.workflows.add(workflow)
    transition_id = EntityId(new_uuid7())
    action = WorkflowAction.create(transition_id=transition_id, action_type=ActionType.CREATE_COMMENT, config={"body": "Later"}, position=1.0)
    await uow.actions.add(action)
    pending = PendingAutomationAction.create(
        workflow_id=workflow.id, task_id=task_id, transition_id=transition_id, action_id=action.id,
        run_at=utcnow() - timedelta(seconds=1), actor_user_id=actor_id,
    )
    await uow.pending_actions.add(pending)

    service = WorkflowAutomationService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), action_executor=action_executor)
    processed = await service.run_due_actions()

    assert processed == 1
    assert uow.pending_actions.pending[pending.id].status.value == "executed"
    entries = await uow.activity_entries.list_for_task(workflow.id, task_id)
    assert len(entries) == 1
    assert entries[0].body == "Later"


@pytest.mark.asyncio
async def test_run_due_actions_ignores_actions_not_yet_due() -> None:
    uow = FakeWorkflowEngineUnitOfWork()
    action_executor = ActionExecutor(tasks_context=FakeTasksContext(), notification_dispatcher=None, user_directory=FakeUserDirectory(), webhook_executor=FakeWebhookExecutor())

    from app.workflow_engine.domain.entities import WorkflowDefinition
    from app.platform_core.shared_kernel.types import EntityId, OrgId

    workflow = WorkflowDefinition.create(project_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), name="Demo")
    await uow.workflows.add(workflow)
    action = WorkflowAction.create(transition_id=EntityId(new_uuid7()), action_type=ActionType.CREATE_COMMENT, config={"body": "Later"}, position=1.0)
    await uow.actions.add(action)
    pending = PendingAutomationAction.create(
        workflow_id=workflow.id, task_id=EntityId(new_uuid7()), transition_id=action.transition_id, action_id=action.id,
        run_at=utcnow() + timedelta(hours=1), actor_user_id=EntityId(new_uuid7()),
    )
    await uow.pending_actions.add(pending)

    service = WorkflowAutomationService(uow_factory=lambda: uow, dispatcher=EventDispatcher(), action_executor=action_executor)
    processed = await service.run_due_actions()

    assert processed == 0
    assert uow.pending_actions.pending[pending.id].status.value == "pending"
