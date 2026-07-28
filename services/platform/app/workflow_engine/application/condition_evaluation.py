"""
Workflow Conditions submodule (6): STATUS, PRIORITY, LABEL, ASSIGNEE,
PROJECT, BOARD, SPRINT, CUSTOM_FIELD.

A pure function, deliberately free of any ACL/repository dependency — the
caller (execution_service.py) resolves the TaskSummary and
BoardPlacementSummary once per evaluation and passes them in, so this
stays trivially unit-testable.

CUSTOM_FIELD is accepted as a valid enum value (the request lists it) but
always evaluates to False: no bounded context in this platform defines a
custom-field concept for tasks to check against yet. Same honesty
precedent as Boards' EPIC swimlane strategy — accept the vocabulary,
don't fabricate the data.
"""

from __future__ import annotations

from typing import Any

from app.workflow_engine.application.ports import BoardPlacementSummary, TaskSummary
from app.workflow_engine.domain.entities import ConditionOperator, ConditionType, WorkflowCondition


def _stringify(value: Any) -> Any:
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return str(value) if value is not None else None


def _apply_operator(actual: Any, operator: ConditionOperator, expected: Any) -> bool:
    actual_s = _stringify(actual)
    expected_s = _stringify(expected)
    if operator == ConditionOperator.EQUALS:
        return actual_s == expected_s
    if operator == ConditionOperator.NOT_EQUALS:
        return actual_s != expected_s
    if operator == ConditionOperator.IN:
        allowed = expected_s if isinstance(expected_s, list) else [expected_s]
        return actual_s in allowed
    if operator == ConditionOperator.CONTAINS:
        collection = actual_s if isinstance(actual_s, list) else [actual_s]
        return expected_s in collection
    return False


def evaluate_condition(condition: WorkflowCondition, *, task: TaskSummary, board_placement: BoardPlacementSummary | None) -> bool:
    if condition.condition_type == ConditionType.STATUS:
        return _apply_operator(task.status, condition.operator, condition.value)
    if condition.condition_type == ConditionType.PRIORITY:
        return _apply_operator(task.priority, condition.operator, condition.value)
    if condition.condition_type == ConditionType.PROJECT:
        return _apply_operator(task.project_id, condition.operator, condition.value)
    if condition.condition_type == ConditionType.LABEL:
        return _apply_operator(task.label_ids, condition.operator, condition.value)
    if condition.condition_type == ConditionType.ASSIGNEE:
        return _apply_operator(task.assignee_ids, condition.operator, condition.value)
    if condition.condition_type == ConditionType.BOARD:
        actual = board_placement.board_id if board_placement else None
        return _apply_operator(actual, condition.operator, condition.value)
    if condition.condition_type == ConditionType.SPRINT:
        actual = board_placement.sprint_id if board_placement else None
        return _apply_operator(actual, condition.operator, condition.value)
    return False  # CUSTOM_FIELD — see module docstring.


def evaluate_conditions(conditions: list[WorkflowCondition], *, task: TaskSummary, board_placement: BoardPlacementSummary | None) -> bool:
    return all(evaluate_condition(c, task=task, board_placement=board_placement) for c in conditions)
