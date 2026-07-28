"""
Workflow Engine domain entities.

WorkflowDefinition is the aggregate root (EventRecordingMixin). States,
Transitions, Rules, Actions, Conditions, TaskState, and the various
tracking join-entities are plain structural entities managed by their own
application services — same convention as every prior context (events for
these are constructed and dispatched at the application layer, not
recorded on the entity itself).

WorkflowTaskState is this context's own record of "which state is this task
currently in, for this workflow" — independent of Task.status (from the
frozen Tasks & Work Management context). A WorkflowState can optionally
carry a `mapped_task_status`; when a transition lands on such a state, the
application layer syncs the underlying Task's real status via the ACL to
Tasks — identical technique to Boards' BoardColumn.mapped_task_status.

Plain Python classes, not pydantic/SQLAlchemy models — same dependency
rule as every other context (ADR-005..009): domain depends only on
shared_kernel/events.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from app.workflow_engine.domain.events import (
    WorkflowArchived,
    WorkflowCreated,
    WorkflowDeleted,
    WorkflowRestored,
    WorkflowUpdated,
)
from app.workflow_engine.domain.exceptions import (
    ApprovalAlreadyDecidedError,
    WorkflowAlreadyArchivedError,
    WorkflowAlreadyDeletedError,
    WorkflowNotActiveError,
    WorkflowNotArchivedError,
)


_POSITION_GAP = 1024.0


def compute_position_between(previous: float | None, following: float | None) -> float:
    """Fractional indexing — identical technique to Boards'/Tasks'
    compute_position_between, reimplemented here (not imported) since
    domain layers never depend on another bounded context, even for a
    small pure function."""
    if previous is None and following is None:
        return _POSITION_GAP
    if previous is None:
        return following - _POSITION_GAP  # type: ignore[operator]
    if following is None:
        return previous + _POSITION_GAP
    return (previous + following) / 2


class WorkflowStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RuleType(StrEnum):
    REQUIRED_ROLE = "required_role"
    REQUIRED_PERMISSION = "required_permission"
    REQUIRED_FIELD_VALUE = "required_field_value"
    REQUIRED_APPROVAL = "required_approval"
    REQUIRED_CHECKLIST_COMPLETION = "required_checklist_completion"


class ActionType(StrEnum):
    ASSIGN_USER = "assign_user"
    CHANGE_PRIORITY = "change_priority"
    SEND_NOTIFICATION = "send_notification"
    CREATE_COMMENT = "create_comment"
    CREATE_ACTIVITY_LOG = "create_activity_log"
    UPDATE_DUE_DATE = "update_due_date"
    EXECUTE_WEBHOOK = "execute_webhook"


class ActionTriggerMode(StrEnum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    DELAYED = "delayed"


class ConditionType(StrEnum):
    STATUS = "status"
    PRIORITY = "priority"
    LABEL = "label"
    ASSIGNEE = "assignee"
    PROJECT = "project"
    BOARD = "board"
    SPRINT = "sprint"
    CUSTOM_FIELD = "custom_field"


class ConditionOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    CONTAINS = "contains"


class PendingActionStatus(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActivityEntryType(StrEnum):
    COMMENT = "comment"
    ACTIVITY_LOG = "activity_log"


class WorkflowDefinition(EventRecordingMixin):
    def __init__(
        self, *, id: EntityId, project_id: EntityId, org_id: OrgId, name: str, description: str,
        status: WorkflowStatus, archived_at: datetime | None = None, deleted_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.project_id = project_id
        self.org_id = org_id
        self.name = name
        self.description = description
        self.status = status
        self.archived_at = archived_at
        self.deleted_at = deleted_at
        self.version = version

    @classmethod
    def create(cls, *, project_id: EntityId, org_id: OrgId, name: str, description: str = "") -> "WorkflowDefinition":
        workflow = cls(
            id=EntityId(new_uuid7()), project_id=project_id, org_id=org_id, name=name, description=description,
            status=WorkflowStatus.ACTIVE,
        )
        workflow.record_event(WorkflowCreated(aggregate_id=workflow.id, project_id=project_id, org_id=org_id, name=name))
        return workflow

    def assert_active(self) -> None:
        if self.status != WorkflowStatus.ACTIVE:
            raise WorkflowNotActiveError(self.status.value)

    def assert_not_deleted(self) -> None:
        if self.deleted_at is not None:
            raise WorkflowAlreadyDeletedError()

    def update(self, *, name: str | None = None, description: str | None = None) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        self.record_event(WorkflowUpdated(aggregate_id=self.id))

    def archive(self) -> None:
        if self.status == WorkflowStatus.ARCHIVED:
            raise WorkflowAlreadyArchivedError()
        self.status = WorkflowStatus.ARCHIVED
        self.archived_at = utcnow()
        self.record_event(WorkflowArchived(aggregate_id=self.id))

    def restore(self) -> None:
        if self.status != WorkflowStatus.ARCHIVED:
            raise WorkflowNotArchivedError()
        self.status = WorkflowStatus.ACTIVE
        self.archived_at = None
        self.record_event(WorkflowRestored(aggregate_id=self.id))

    def mark_deleted(self) -> None:
        self.assert_not_deleted()
        self.deleted_at = utcnow()
        self.record_event(WorkflowDeleted(aggregate_id=self.id))


class WorkflowState:
    def __init__(
        self, *, id: EntityId, workflow_id: EntityId, name: str, position: float, is_initial: bool = False,
        is_final: bool = False, is_hidden: bool = False, is_archived: bool = False,
        mapped_task_status: str | None = None, version: int = 1,
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.name = name
        self.position = position
        self.is_initial = is_initial
        self.is_final = is_final
        self.is_hidden = is_hidden
        self.is_archived = is_archived
        self.mapped_task_status = mapped_task_status
        self.version = version

    @classmethod
    def create(
        cls, *, workflow_id: EntityId, name: str, position: float, is_initial: bool = False, is_final: bool = False,
        is_hidden: bool = False, mapped_task_status: str | None = None,
    ) -> "WorkflowState":
        return cls(
            id=EntityId(new_uuid7()), workflow_id=workflow_id, name=name, position=position, is_initial=is_initial,
            is_final=is_final, is_hidden=is_hidden, mapped_task_status=mapped_task_status,
        )

    def rename(self, name: str) -> None:
        self.name = name

    def set_initial(self, is_initial: bool) -> None:
        self.is_initial = is_initial

    def set_final(self, is_final: bool) -> None:
        self.is_final = is_final

    def set_hidden(self, is_hidden: bool) -> None:
        self.is_hidden = is_hidden

    def set_archived(self, is_archived: bool) -> None:
        self.is_archived = is_archived

    def set_mapped_task_status(self, status: str | None) -> None:
        self.mapped_task_status = status

    def set_position(self, position: float) -> None:
        self.position = position


class WorkflowTransition:
    def __init__(
        self, *, id: EntityId, workflow_id: EntityId, name: str, from_state_id: EntityId, to_state_id: EntityId,
        position: float, enabled: bool = True, is_automatic: bool = False, version: int = 1,
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.name = name
        self.from_state_id = from_state_id
        self.to_state_id = to_state_id
        self.position = position
        self.enabled = enabled
        self.is_automatic = is_automatic
        self.version = version

    @classmethod
    def create(
        cls, *, workflow_id: EntityId, name: str, from_state_id: EntityId, to_state_id: EntityId, position: float,
        is_automatic: bool = False,
    ) -> "WorkflowTransition":
        return cls(
            id=EntityId(new_uuid7()), workflow_id=workflow_id, name=name, from_state_id=from_state_id,
            to_state_id=to_state_id, position=position, is_automatic=is_automatic,
        )

    def rename(self, name: str) -> None:
        self.name = name

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def set_automatic(self, is_automatic: bool) -> None:
        self.is_automatic = is_automatic

    def set_position(self, position: float) -> None:
        self.position = position


class TransitionRule:
    def __init__(self, *, id: EntityId, transition_id: EntityId, rule_type: RuleType, config: dict[str, Any]) -> None:
        self.id = id
        self.transition_id = transition_id
        self.rule_type = rule_type
        self.config = config

    @classmethod
    def create(cls, *, transition_id: EntityId, rule_type: RuleType, config: dict[str, Any]) -> "TransitionRule":
        return cls(id=EntityId(new_uuid7()), transition_id=transition_id, rule_type=rule_type, config=config)


class WorkflowAction:
    def __init__(
        self, *, id: EntityId, transition_id: EntityId, action_type: ActionType, config: dict[str, Any],
        position: float, trigger_mode: ActionTriggerMode = ActionTriggerMode.IMMEDIATE,
        delay_seconds: float | None = None, scheduled_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.transition_id = transition_id
        self.action_type = action_type
        self.config = config
        self.position = position
        self.trigger_mode = trigger_mode
        self.delay_seconds = delay_seconds
        self.scheduled_at = scheduled_at

    @classmethod
    def create(
        cls, *, transition_id: EntityId, action_type: ActionType, config: dict[str, Any], position: float,
        trigger_mode: ActionTriggerMode = ActionTriggerMode.IMMEDIATE, delay_seconds: float | None = None,
        scheduled_at: datetime | None = None,
    ) -> "WorkflowAction":
        return cls(
            id=EntityId(new_uuid7()), transition_id=transition_id, action_type=action_type, config=config,
            position=position, trigger_mode=trigger_mode, delay_seconds=delay_seconds, scheduled_at=scheduled_at,
        )

    def compute_run_at(self, *, base_time: datetime) -> datetime:
        """Resolves this action's due time once a transition actually
        executes — DELAYED is relative to that moment, SCHEDULED is an
        absolute timestamp captured up front."""
        if self.trigger_mode == ActionTriggerMode.DELAYED and self.delay_seconds is not None:
            from datetime import timedelta

            return base_time + timedelta(seconds=self.delay_seconds)
        if self.trigger_mode == ActionTriggerMode.SCHEDULED and self.scheduled_at is not None:
            return self.scheduled_at
        return base_time


class WorkflowCondition:
    def __init__(
        self, *, id: EntityId, transition_id: EntityId, condition_type: ConditionType, operator: ConditionOperator,
        value: Any, position: float,
    ) -> None:
        self.id = id
        self.transition_id = transition_id
        self.condition_type = condition_type
        self.operator = operator
        self.value = value
        self.position = position

    @classmethod
    def create(
        cls, *, transition_id: EntityId, condition_type: ConditionType, operator: ConditionOperator, value: Any,
        position: float,
    ) -> "WorkflowCondition":
        return cls(
            id=EntityId(new_uuid7()), transition_id=transition_id, condition_type=condition_type, operator=operator,
            value=value, position=position,
        )


class WorkflowTaskState:
    """This context's own record of which state a Task currently occupies
    within a given workflow. Independent of Task.status — kept in sync one
    direction via WorkflowState.mapped_task_status when configured."""

    def __init__(
        self, *, id: EntityId, workflow_id: EntityId, task_id: EntityId, current_state_id: EntityId,
        updated_at: datetime | None = None, version: int = 1,
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.current_state_id = current_state_id
        self.updated_at = updated_at or utcnow()
        self.version = version

    @classmethod
    def create(cls, *, workflow_id: EntityId, task_id: EntityId, initial_state_id: EntityId) -> "WorkflowTaskState":
        return cls(id=EntityId(new_uuid7()), workflow_id=workflow_id, task_id=task_id, current_state_id=initial_state_id)

    def move_to_state(self, state_id: EntityId) -> None:
        self.current_state_id = state_id
        self.updated_at = utcnow()


class WorkflowExecutionRecord:
    """Append-only — the Audit Trail submodule (8) literally requires:
    every transition, previous state, new state, actor, timestamp, reason."""

    def __init__(
        self, *, id: EntityId, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId,
        from_state_id: EntityId, to_state_id: EntityId, actor_user_id: EntityId, reason: str,
        occurred_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.transition_id = transition_id
        self.from_state_id = from_state_id
        self.to_state_id = to_state_id
        self.actor_user_id = actor_user_id
        self.reason = reason
        self.occurred_at = occurred_at or utcnow()

    @classmethod
    def create(
        cls, *, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId, from_state_id: EntityId,
        to_state_id: EntityId, actor_user_id: EntityId, reason: str = "",
    ) -> "WorkflowExecutionRecord":
        return cls(
            id=EntityId(new_uuid7()), workflow_id=workflow_id, task_id=task_id, transition_id=transition_id,
            from_state_id=from_state_id, to_state_id=to_state_id, actor_user_id=actor_user_id, reason=reason,
        )


class PendingAutomationAction:
    """A scheduled or delayed WorkflowAction waiting to fire — scanned and
    executed by the recurring automation job (application/automation_service.py
    + composition.py's JobScheduler entry, same infra pattern Tasks/Boards
    both already established)."""

    def __init__(
        self, *, id: EntityId, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId, action_id: EntityId,
        run_at: datetime, actor_user_id: EntityId, status: PendingActionStatus = PendingActionStatus.PENDING,
        created_at: datetime | None = None, executed_at: datetime | None = None, failure_reason: str | None = None,
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.transition_id = transition_id
        self.action_id = action_id
        self.run_at = run_at
        # The actor who triggered the transition that scheduled this action
        # — carried forward so a DELAYED/SCHEDULED action executes under the
        # same identity an IMMEDIATE one would have, rather than needing a
        # fabricated "system" actor that downstream ACL authorization checks
        # (e.g. Tasks' project-membership check) would reject.
        self.actor_user_id = actor_user_id
        self.status = status
        self.created_at = created_at or utcnow()
        self.executed_at = executed_at
        self.failure_reason = failure_reason

    @classmethod
    def create(
        cls, *, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId, action_id: EntityId,
        run_at: datetime, actor_user_id: EntityId,
    ) -> "PendingAutomationAction":
        return cls(
            id=EntityId(new_uuid7()), workflow_id=workflow_id, task_id=task_id, transition_id=transition_id,
            action_id=action_id, run_at=run_at, actor_user_id=actor_user_id,
        )

    def mark_executed(self) -> None:
        self.status = PendingActionStatus.EXECUTED
        self.executed_at = utcnow()

    def mark_failed(self, reason: str) -> None:
        self.status = PendingActionStatus.FAILED
        self.executed_at = utcnow()
        self.failure_reason = reason

    def cancel(self) -> None:
        self.status = PendingActionStatus.CANCELLED


class WorkflowApprovalRequest:
    def __init__(
        self, *, id: EntityId, transition_id: EntityId, task_id: EntityId, requested_by: EntityId,
        status: ApprovalStatus = ApprovalStatus.PENDING, requested_at: datetime | None = None,
        decided_by: EntityId | None = None, decided_at: datetime | None = None, reason: str = "",
    ) -> None:
        self.id = id
        self.transition_id = transition_id
        self.task_id = task_id
        self.requested_by = requested_by
        self.status = status
        self.requested_at = requested_at or utcnow()
        self.decided_by = decided_by
        self.decided_at = decided_at
        self.reason = reason

    @classmethod
    def create(cls, *, transition_id: EntityId, task_id: EntityId, requested_by: EntityId) -> "WorkflowApprovalRequest":
        return cls(id=EntityId(new_uuid7()), transition_id=transition_id, task_id=task_id, requested_by=requested_by)

    def approve(self, *, decided_by: EntityId, reason: str = "") -> None:
        if self.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecidedError()
        self.status = ApprovalStatus.APPROVED
        self.decided_by = decided_by
        self.decided_at = utcnow()
        self.reason = reason

    def reject(self, *, decided_by: EntityId, reason: str = "") -> None:
        if self.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecidedError()
        self.status = ApprovalStatus.REJECTED
        self.decided_by = decided_by
        self.decided_at = utcnow()
        self.reason = reason


class WorkflowChecklistItem:
    """A required-checklist template attached to a transition — completion
    is tracked per-task via WorkflowChecklistCompletion. Self-contained
    within Workflow Engine since no other bounded context defines a
    checklist concept."""

    def __init__(self, *, id: EntityId, transition_id: EntityId, label: str, position: float, version: int = 1) -> None:
        self.id = id
        self.transition_id = transition_id
        self.label = label
        self.position = position
        self.version = version

    @classmethod
    def create(cls, *, transition_id: EntityId, label: str, position: float) -> "WorkflowChecklistItem":
        return cls(id=EntityId(new_uuid7()), transition_id=transition_id, label=label, position=position)

    def rename(self, label: str) -> None:
        self.label = label

    def set_position(self, position: float) -> None:
        self.position = position


class WorkflowChecklistCompletion:
    def __init__(
        self, *, id: EntityId, checklist_item_id: EntityId, task_id: EntityId, completed_by: EntityId,
        completed_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.checklist_item_id = checklist_item_id
        self.task_id = task_id
        self.completed_by = completed_by
        self.completed_at = completed_at or utcnow()

    @classmethod
    def create(cls, *, checklist_item_id: EntityId, task_id: EntityId, completed_by: EntityId) -> "WorkflowChecklistCompletion":
        return cls(id=EntityId(new_uuid7()), checklist_item_id=checklist_item_id, task_id=task_id, completed_by=completed_by)


class WorkflowActivityEntry:
    """Append-only — backs both the CREATE_COMMENT and CREATE_ACTIVITY_LOG
    workflow actions. Tasks & Work Management has no comment/activity-log
    concept of its own to reuse, so this stays a genuine, self-contained
    record scoped to the workflow rather than a fabricated write into
    another context."""

    def __init__(
        self, *, id: EntityId, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId | None,
        entry_type: ActivityEntryType, body: str, actor_user_id: EntityId, occurred_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.transition_id = transition_id
        self.entry_type = entry_type
        self.body = body
        self.actor_user_id = actor_user_id
        self.occurred_at = occurred_at or utcnow()

    @classmethod
    def create(
        cls, *, workflow_id: EntityId, task_id: EntityId, transition_id: EntityId | None, entry_type: ActivityEntryType,
        body: str, actor_user_id: EntityId,
    ) -> "WorkflowActivityEntry":
        return cls(
            id=EntityId(new_uuid7()), workflow_id=workflow_id, task_id=task_id, transition_id=transition_id,
            entry_type=entry_type, body=body, actor_user_id=actor_user_id,
        )
