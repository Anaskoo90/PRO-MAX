from datetime import timedelta

import pytest

from app.workflow_engine.domain.entities import (
    ActionTriggerMode,
    ActionType,
    ActivityEntryType,
    ConditionOperator,
    ConditionType,
    PendingAutomationAction,
    RuleType,
    TransitionRule,
    WorkflowAction,
    WorkflowApprovalRequest,
    WorkflowChecklistCompletion,
    WorkflowChecklistItem,
    WorkflowCondition,
    WorkflowActivityEntry,
    WorkflowDefinition,
    WorkflowExecutionRecord,
    WorkflowState,
    WorkflowTaskState,
    WorkflowTransition,
    compute_position_between,
)
from app.workflow_engine.domain.exceptions import (
    ApprovalAlreadyDecidedError,
    WorkflowAlreadyArchivedError,
    WorkflowAlreadyDeletedError,
    WorkflowNotArchivedError,
)
from app.workflow_engine.domain.events import WorkflowCreated
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


def _new_workflow(**kwargs) -> WorkflowDefinition:
    return WorkflowDefinition.create(project_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), name="Bug Triage", **kwargs)


def test_create_workflow_records_workflow_created_event() -> None:
    workflow = _new_workflow()
    events = workflow.pull_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], WorkflowCreated)


def test_archive_then_restore_round_trips() -> None:
    workflow = _new_workflow()
    workflow.archive()
    assert workflow.status.value == "archived"
    assert workflow.archived_at is not None

    workflow.restore()
    assert workflow.status.value == "active"
    assert workflow.archived_at is None


def test_archiving_twice_raises() -> None:
    workflow = _new_workflow()
    workflow.archive()
    with pytest.raises(WorkflowAlreadyArchivedError):
        workflow.archive()


def test_restoring_a_non_archived_workflow_raises() -> None:
    workflow = _new_workflow()
    with pytest.raises(WorkflowNotArchivedError):
        workflow.restore()


def test_mark_deleted_twice_raises() -> None:
    workflow = _new_workflow()
    workflow.mark_deleted()
    with pytest.raises(WorkflowAlreadyDeletedError):
        workflow.mark_deleted()


def test_state_flags_and_mapped_task_status() -> None:
    workflow_id = EntityId(new_uuid7())
    state = WorkflowState.create(workflow_id=workflow_id, name="Done", position=1.0, is_final=True, mapped_task_status="done")
    assert state.is_final is True
    assert state.mapped_task_status == "done"

    state.set_hidden(True)
    state.set_archived(True)
    assert state.is_hidden is True
    assert state.is_archived is True


def test_transition_enable_disable_and_automatic_flag() -> None:
    workflow_id = EntityId(new_uuid7())
    from_state = WorkflowState.create(workflow_id=workflow_id, name="Todo", position=1.0)
    to_state = WorkflowState.create(workflow_id=workflow_id, name="Done", position=2.0)
    transition = WorkflowTransition.create(workflow_id=workflow_id, name="Complete", from_state_id=from_state.id, to_state_id=to_state.id, position=1.0)

    assert transition.enabled is True
    transition.disable()
    assert transition.enabled is False
    transition.enable()
    assert transition.enabled is True

    transition.set_automatic(True)
    assert transition.is_automatic is True


def test_transition_rule_action_condition_creation() -> None:
    transition_id = EntityId(new_uuid7())
    rule = TransitionRule.create(transition_id=transition_id, rule_type=RuleType.REQUIRED_ROLE, config={"roles": ["owner"]})
    assert rule.config["roles"] == ["owner"]

    action = WorkflowAction.create(
        transition_id=transition_id, action_type=ActionType.SEND_NOTIFICATION, config={"body": "hi"}, position=1.0,
        trigger_mode=ActionTriggerMode.DELAYED, delay_seconds=120,
    )
    run_at = action.compute_run_at(base_time=utcnow())
    assert run_at > utcnow()

    condition = WorkflowCondition.create(transition_id=transition_id, condition_type=ConditionType.PRIORITY, operator=ConditionOperator.EQUALS, value="high", position=1.0)
    assert condition.condition_type == ConditionType.PRIORITY


def test_action_scheduled_trigger_uses_absolute_timestamp() -> None:
    transition_id = EntityId(new_uuid7())
    scheduled_at = utcnow() + timedelta(days=1)
    action = WorkflowAction.create(
        transition_id=transition_id, action_type=ActionType.EXECUTE_WEBHOOK, config={"url": "https://example.com"},
        position=1.0, trigger_mode=ActionTriggerMode.SCHEDULED, scheduled_at=scheduled_at,
    )
    assert action.compute_run_at(base_time=utcnow()) == scheduled_at


def test_workflow_task_state_move_to_state() -> None:
    workflow_id = EntityId(new_uuid7())
    task_id = EntityId(new_uuid7())
    initial_state_id = EntityId(new_uuid7())
    task_state = WorkflowTaskState.create(workflow_id=workflow_id, task_id=task_id, initial_state_id=initial_state_id)
    assert task_state.current_state_id == initial_state_id

    next_state_id = EntityId(new_uuid7())
    task_state.move_to_state(next_state_id)
    assert task_state.current_state_id == next_state_id


def test_execution_record_is_append_only_snapshot() -> None:
    record = WorkflowExecutionRecord.create(
        workflow_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), transition_id=EntityId(new_uuid7()),
        from_state_id=EntityId(new_uuid7()), to_state_id=EntityId(new_uuid7()), actor_user_id=EntityId(new_uuid7()),
        reason="manual triage",
    )
    assert record.reason == "manual triage"
    assert record.occurred_at is not None


def test_pending_automation_action_lifecycle() -> None:
    pending = PendingAutomationAction.create(
        workflow_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), transition_id=EntityId(new_uuid7()),
        action_id=EntityId(new_uuid7()), run_at=utcnow(), actor_user_id=EntityId(new_uuid7()),
    )
    assert pending.status.value == "pending"
    pending.mark_executed()
    assert pending.status.value == "executed"
    assert pending.executed_at is not None


def test_pending_automation_action_can_fail_or_cancel() -> None:
    pending = PendingAutomationAction.create(
        workflow_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), transition_id=EntityId(new_uuid7()),
        action_id=EntityId(new_uuid7()), run_at=utcnow(), actor_user_id=EntityId(new_uuid7()),
    )
    pending.mark_failed("webhook timed out")
    assert pending.status.value == "failed"
    assert pending.failure_reason == "webhook timed out"

    other = PendingAutomationAction.create(
        workflow_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), transition_id=EntityId(new_uuid7()),
        action_id=EntityId(new_uuid7()), run_at=utcnow(), actor_user_id=EntityId(new_uuid7()),
    )
    other.cancel()
    assert other.status.value == "cancelled"


def test_approval_request_approve_and_reject() -> None:
    approval = WorkflowApprovalRequest.create(transition_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), requested_by=EntityId(new_uuid7()))
    approval.approve(decided_by=EntityId(new_uuid7()), reason="looks good")
    assert approval.status.value == "approved"
    assert approval.reason == "looks good"


def test_approval_request_cannot_be_decided_twice() -> None:
    approval = WorkflowApprovalRequest.create(transition_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), requested_by=EntityId(new_uuid7()))
    approval.reject(decided_by=EntityId(new_uuid7()))
    with pytest.raises(ApprovalAlreadyDecidedError):
        approval.approve(decided_by=EntityId(new_uuid7()))


def test_checklist_item_and_completion() -> None:
    transition_id = EntityId(new_uuid7())
    task_id = EntityId(new_uuid7())
    item = WorkflowChecklistItem.create(transition_id=transition_id, label="Confirm repro steps", position=1.0)
    completion = WorkflowChecklistCompletion.create(checklist_item_id=item.id, task_id=task_id, completed_by=EntityId(new_uuid7()))
    assert completion.checklist_item_id == item.id
    assert completion.task_id == task_id


def test_activity_entry_supports_comment_and_activity_log_types() -> None:
    comment = WorkflowActivityEntry.create(
        workflow_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), transition_id=EntityId(new_uuid7()),
        entry_type=ActivityEntryType.COMMENT, body="Looks good", actor_user_id=EntityId(new_uuid7()),
    )
    assert comment.entry_type == ActivityEntryType.COMMENT

    log_entry = WorkflowActivityEntry.create(
        workflow_id=EntityId(new_uuid7()), task_id=EntityId(new_uuid7()), transition_id=None,
        entry_type=ActivityEntryType.ACTIVITY_LOG, body="Transitioned automatically", actor_user_id=EntityId(new_uuid7()),
    )
    assert log_entry.transition_id is None


def test_compute_position_between_inserts_correctly() -> None:
    first = compute_position_between(None, None)
    after_first = compute_position_between(first, None)
    between = compute_position_between(first, after_first)
    before_first = compute_position_between(None, first)

    assert first < between < after_first
    assert before_first < first
