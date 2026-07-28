from app.workflow_engine.application.condition_evaluation import evaluate_condition, evaluate_conditions
from app.workflow_engine.application.ports import BoardPlacementSummary, TaskSummary
from app.workflow_engine.domain.entities import ConditionOperator, ConditionType, WorkflowCondition
from app.platform_core.shared_kernel.utils import new_uuid7


def _task(**overrides) -> TaskSummary:
    defaults = dict(
        id=new_uuid7(), project_id=new_uuid7(), org_id=new_uuid7(), title="Demo", status="in_progress",
        priority="high", assignee_ids=(), label_ids=(),
    )
    defaults.update(overrides)
    return TaskSummary(**defaults)


def _condition(condition_type: ConditionType, operator: ConditionOperator, value) -> WorkflowCondition:
    return WorkflowCondition.create(transition_id=new_uuid7(), condition_type=condition_type, operator=operator, value=value, position=1.0)


def test_status_equals_matches() -> None:
    task = _task(status="done")
    condition = _condition(ConditionType.STATUS, ConditionOperator.EQUALS, "done")
    assert evaluate_condition(condition, task=task, board_placement=None) is True


def test_status_not_equals() -> None:
    task = _task(status="done")
    condition = _condition(ConditionType.STATUS, ConditionOperator.NOT_EQUALS, "done")
    assert evaluate_condition(condition, task=task, board_placement=None) is False


def test_priority_in_list() -> None:
    task = _task(priority="critical")
    condition = _condition(ConditionType.PRIORITY, ConditionOperator.IN, ["high", "critical"])
    assert evaluate_condition(condition, task=task, board_placement=None) is True


def test_label_contains() -> None:
    label_id = new_uuid7()
    task = _task(label_ids=(label_id,))
    condition = _condition(ConditionType.LABEL, ConditionOperator.CONTAINS, str(label_id))
    assert evaluate_condition(condition, task=task, board_placement=None) is True


def test_assignee_contains_false_when_not_assigned() -> None:
    task = _task(assignee_ids=(new_uuid7(),))
    condition = _condition(ConditionType.ASSIGNEE, ConditionOperator.CONTAINS, str(new_uuid7()))
    assert evaluate_condition(condition, task=task, board_placement=None) is False


def test_board_condition_uses_board_placement() -> None:
    board_id = new_uuid7()
    task = _task()
    placement = BoardPlacementSummary(board_id=board_id, column_id=None, sprint_id=None)
    condition = _condition(ConditionType.BOARD, ConditionOperator.EQUALS, str(board_id))
    assert evaluate_condition(condition, task=task, board_placement=placement) is True


def test_sprint_condition_false_when_no_placement() -> None:
    task = _task()
    condition = _condition(ConditionType.SPRINT, ConditionOperator.EQUALS, str(new_uuid7()))
    assert evaluate_condition(condition, task=task, board_placement=None) is False


def test_custom_field_condition_always_false() -> None:
    """Honest gap: no bounded context defines custom fields for tasks yet."""
    task = _task()
    condition = _condition(ConditionType.CUSTOM_FIELD, ConditionOperator.EQUALS, "anything")
    assert evaluate_condition(condition, task=task, board_placement=None) is False


def test_evaluate_conditions_requires_all_to_pass() -> None:
    task = _task(status="done", priority="high")
    conditions = [
        _condition(ConditionType.STATUS, ConditionOperator.EQUALS, "done"),
        _condition(ConditionType.PRIORITY, ConditionOperator.EQUALS, "low"),
    ]
    assert evaluate_conditions(conditions, task=task, board_placement=None) is False


def test_evaluate_conditions_empty_list_passes() -> None:
    task = _task()
    assert evaluate_conditions([], task=task, board_placement=None) is True
