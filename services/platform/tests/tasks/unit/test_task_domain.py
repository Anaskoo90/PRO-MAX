from datetime import timedelta

import pytest

from app.tasks.domain.entities import Task, compute_position_between
from app.tasks.domain.events import TaskDuplicated
from app.tasks.domain.exceptions import (
    InvalidDateRangeError,
    InvalidTaskStatusTransitionError,
    TaskAlreadyArchivedError,
    TaskAlreadyDeletedError,
    TaskCannotBeOwnParentError,
    TaskNotArchivedError,
)
from app.tasks.domain.workflow import DEFAULT_WORKFLOW, TaskPriority, TaskStatus
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


def _new_task(**kwargs) -> Task:
    return Task.create(project_id=EntityId(new_uuid7()), org_id=OrgId(new_uuid7()), title="Demo", **kwargs)


def test_create_starts_in_backlog_with_medium_priority() -> None:
    task = _new_task()
    assert task.status == TaskStatus.BACKLOG
    assert task.priority == TaskPriority.MEDIUM


def test_valid_status_transition_through_default_workflow() -> None:
    task = _new_task()
    for status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.TESTING, TaskStatus.DONE):
        task.change_status(status, workflow=DEFAULT_WORKFLOW)
    assert task.status == TaskStatus.DONE
    assert task.completion_date is not None


def test_invalid_status_transition_raises() -> None:
    task = _new_task()
    with pytest.raises(InvalidTaskStatusTransitionError):
        task.change_status(TaskStatus.DONE, workflow=DEFAULT_WORKFLOW)


def test_reopening_a_done_task_clears_completion_date() -> None:
    task = _new_task()
    for status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.TESTING, TaskStatus.DONE):
        task.change_status(status, workflow=DEFAULT_WORKFLOW)
    task.change_status(TaskStatus.IN_PROGRESS, workflow=DEFAULT_WORKFLOW)
    assert task.completion_date is None


def test_same_status_transition_is_a_no_op() -> None:
    task = _new_task()
    task.change_status(TaskStatus.BACKLOG, workflow=DEFAULT_WORKFLOW)
    assert task.status == TaskStatus.BACKLOG


def test_overdue_detection() -> None:
    overdue = _new_task(due_date=utcnow() - timedelta(days=1))
    not_overdue = _new_task(due_date=utcnow() + timedelta(days=1))
    no_due_date = _new_task()

    assert overdue.is_overdue() is True
    assert not_overdue.is_overdue() is False
    assert no_due_date.is_overdue() is False


def test_terminal_status_task_is_never_overdue() -> None:
    task = _new_task(due_date=utcnow() - timedelta(days=1))
    task.change_status(TaskStatus.CANCELLED, workflow=DEFAULT_WORKFLOW)
    assert task.is_overdue() is False


def test_set_dates_rejects_start_after_due() -> None:
    task = _new_task()
    with pytest.raises(InvalidDateRangeError):
        task.set_dates(start_date=utcnow(), due_date=utcnow() - timedelta(days=1))


def test_task_cannot_be_its_own_parent() -> None:
    task = _new_task()
    with pytest.raises(TaskCannotBeOwnParentError):
        task.set_parent(task.id)


def test_archive_then_restore_round_trips() -> None:
    task = _new_task()
    task.archive()
    assert task.is_archived is True
    assert task.archived_at is not None

    task.restore()
    assert task.is_archived is False
    assert task.archived_at is None


def test_archiving_twice_raises() -> None:
    task = _new_task()
    task.archive()
    with pytest.raises(TaskAlreadyArchivedError):
        task.archive()


def test_restoring_a_non_archived_task_raises() -> None:
    task = _new_task()
    with pytest.raises(TaskNotArchivedError):
        task.restore()


def test_mark_deleted_twice_raises() -> None:
    task = _new_task()
    task.mark_deleted()
    with pytest.raises(TaskAlreadyDeletedError):
        task.mark_deleted()


def test_duplicate_starts_fresh_in_backlog_with_only_a_duplicated_event() -> None:
    source = _new_task()
    source.change_status(TaskStatus.TODO, workflow=DEFAULT_WORKFLOW)
    source.change_status(TaskStatus.IN_PROGRESS, workflow=DEFAULT_WORKFLOW)

    duplicate = Task.duplicate_from(source, title="Copy")
    events = duplicate.pull_domain_events()

    assert duplicate.status == TaskStatus.BACKLOG
    assert duplicate.title == "Copy"
    assert duplicate.id != source.id
    assert len(events) == 1
    assert isinstance(events[0], TaskDuplicated)
    assert events[0].source_task_id == source.id


def test_compute_position_between_inserts_correctly() -> None:
    first = compute_position_between(None, None)
    after_first = compute_position_between(first, None)
    between = compute_position_between(first, after_first)
    before_first = compute_position_between(None, first)

    assert first < between < after_first
    assert before_first < first
