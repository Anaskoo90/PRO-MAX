"""
Task Lifecycle: the fixed vocabulary of statuses (TaskStatus) is not
configurable — but which subset is active for a project, and which
transitions between them are allowed, is. WorkflowDefinition is that
per-project configuration; DEFAULT_WORKFLOW is applied whenever a project
has none of its own (looked up by the application layer, never baked into
Task itself, so a later-changed workflow doesn't require touching every
existing task row).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.tasks.domain.events import WorkflowDefinitionCreated, WorkflowDefinitionUpdated
from app.tasks.domain.exceptions import InvalidWorkflowDefinitionError


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    TESTING = "testing"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# The out-of-the-box linear-ish workflow: every status reachable, Blocked/
# Cancelled available as an escape hatch from any active state, Done/
# Cancelled both reopenable rather than being hard dead ends.
DEFAULT_WORKFLOW_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.BACKLOG: frozenset({TaskStatus.TODO, TaskStatus.CANCELLED}),
    TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.REVIEW, TaskStatus.BLOCKED, TaskStatus.TODO, TaskStatus.CANCELLED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.TESTING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}),
    TaskStatus.TESTING: frozenset({TaskStatus.DONE, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.TODO, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.BACKLOG, TaskStatus.TODO}),
}
DEFAULT_WORKFLOW_STATUSES: tuple[TaskStatus, ...] = tuple(TaskStatus)


class Workflow(Protocol):
    """Structural interface both WorkflowDefinition and DefaultWorkflow
    satisfy — Task.change_status accepts anything shaped like this."""

    def is_valid_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool: ...

    def initial_status(self) -> TaskStatus: ...


class WorkflowDefinition(EventRecordingMixin):
    """A project's configured subset of TaskStatus values + allowed
    transitions. Falls back to DEFAULT_WORKFLOW_TRANSITIONS/_STATUSES when a
    project has no WorkflowDefinition row — see workflow_management.py's
    `resolve_workflow_for_project`."""

    def __init__(
        self,
        *,
        id: EntityId,
        project_id: EntityId,
        name: str,
        statuses: tuple[TaskStatus, ...],
        transitions: dict[TaskStatus, frozenset[TaskStatus]],
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.project_id = project_id
        self.name = name
        self.statuses = statuses
        self.transitions = transitions
        self.version = version
        self._validate()

    def _validate(self) -> None:
        if not self.statuses:
            raise InvalidWorkflowDefinitionError("a workflow must include at least one status")
        status_set = set(self.statuses)
        for from_status, allowed in self.transitions.items():
            if from_status not in status_set:
                raise InvalidWorkflowDefinitionError(f"transition source '{from_status}' is not in the workflow's status set")
            unknown = allowed - status_set
            if unknown:
                raise InvalidWorkflowDefinitionError(
                    f"transition target(s) {sorted(u.value for u in unknown)} are not in the workflow's status set"
                )

    @classmethod
    def create(
        cls,
        *,
        project_id: EntityId,
        name: str,
        statuses: tuple[TaskStatus, ...],
        transitions: dict[TaskStatus, frozenset[TaskStatus]],
    ) -> "WorkflowDefinition":
        workflow = cls(id=EntityId(new_uuid7()), project_id=project_id, name=name, statuses=statuses, transitions=transitions)
        workflow.record_event(WorkflowDefinitionCreated(aggregate_id=workflow.id, project_id=project_id, name=name))
        return workflow

    def update(
        self, *, name: str | None = None, statuses: tuple[TaskStatus, ...] | None = None,
        transitions: dict[TaskStatus, frozenset[TaskStatus]] | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if statuses is not None:
            self.statuses = statuses
        if transitions is not None:
            self.transitions = transitions
        self._validate()
        self.record_event(WorkflowDefinitionUpdated(aggregate_id=self.id))

    def is_valid_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        if from_status == to_status:
            return True
        return to_status in self.transitions.get(from_status, frozenset())

    def initial_status(self) -> TaskStatus:
        return self.statuses[0]


class DefaultWorkflow:
    """A zero-configuration stand-in satisfying the same interface as
    WorkflowDefinition, used whenever a project has no custom one."""

    statuses = DEFAULT_WORKFLOW_STATUSES
    transitions = DEFAULT_WORKFLOW_TRANSITIONS

    def is_valid_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        if from_status == to_status:
            return True
        return to_status in DEFAULT_WORKFLOW_TRANSITIONS.get(from_status, frozenset())

    def initial_status(self) -> TaskStatus:
        return TaskStatus.BACKLOG


DEFAULT_WORKFLOW = DefaultWorkflow()
