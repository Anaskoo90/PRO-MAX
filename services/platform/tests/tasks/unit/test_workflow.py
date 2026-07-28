import pytest

from app.tasks.domain.events import WorkflowDefinitionCreated
from app.tasks.domain.exceptions import InvalidWorkflowDefinitionError
from app.tasks.domain.workflow import TaskStatus, WorkflowDefinition
from app.platform_core.shared_kernel.types import EntityId
from app.platform_core.shared_kernel.utils import new_uuid7


def test_create_a_simple_two_status_workflow() -> None:
    workflow = WorkflowDefinition.create(
        project_id=EntityId(new_uuid7()), name="Simple",
        statuses=(TaskStatus.TODO, TaskStatus.DONE),
        transitions={TaskStatus.TODO: frozenset({TaskStatus.DONE})},
    )
    assert workflow.is_valid_transition(TaskStatus.TODO, TaskStatus.DONE) is True
    assert workflow.is_valid_transition(TaskStatus.DONE, TaskStatus.TODO) is False
    events = workflow.pull_domain_events()
    assert isinstance(events[0], WorkflowDefinitionCreated)


def test_transition_source_must_be_in_status_set() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        WorkflowDefinition.create(
            project_id=EntityId(new_uuid7()), name="Bad",
            statuses=(TaskStatus.TODO,),
            transitions={TaskStatus.DONE: frozenset({TaskStatus.TODO})},
        )


def test_transition_target_must_be_in_status_set() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        WorkflowDefinition.create(
            project_id=EntityId(new_uuid7()), name="Bad",
            statuses=(TaskStatus.TODO,),
            transitions={TaskStatus.TODO: frozenset({TaskStatus.DONE})},
        )


def test_empty_status_set_is_rejected() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        WorkflowDefinition.create(project_id=EntityId(new_uuid7()), name="Empty", statuses=(), transitions={})


def test_initial_status_is_the_first_configured_status() -> None:
    workflow = WorkflowDefinition.create(
        project_id=EntityId(new_uuid7()), name="Simple",
        statuses=(TaskStatus.BACKLOG, TaskStatus.DONE),
        transitions={TaskStatus.BACKLOG: frozenset({TaskStatus.DONE})},
    )
    assert workflow.initial_status() == TaskStatus.BACKLOG


def test_update_replaces_statuses_and_transitions() -> None:
    workflow = WorkflowDefinition.create(
        project_id=EntityId(new_uuid7()), name="Simple",
        statuses=(TaskStatus.TODO, TaskStatus.DONE),
        transitions={TaskStatus.TODO: frozenset({TaskStatus.DONE})},
    )
    workflow.pull_domain_events()
    workflow.update(statuses=(TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE), transitions={
        TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS}),
        TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE}),
    })
    assert workflow.is_valid_transition(TaskStatus.TODO, TaskStatus.IN_PROGRESS) is True
    assert workflow.is_valid_transition(TaskStatus.TODO, TaskStatus.DONE) is False
