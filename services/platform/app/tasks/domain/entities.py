"""
Tasks & Work Management domain entities.

Task is the aggregate root. Assignment, labels, dependencies, and related-
task links are all plain join entities (no EventRecordingMixin) managed by
their own application services — identical convention to Identity's
TeamMembership/UserRoleAssignment and Projects' WorkspaceMembership/
ProjectMembership: events for these are constructed and dispatched at the
application layer, not recorded on the entity itself.

Plain Python classes, not pydantic/SQLAlchemy models — same dependency
rule as every other context (ADR-005..009): domain depends only on
shared_kernel/events.
"""

from __future__ import annotations

from datetime import datetime

from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from app.tasks.domain.events import (
    LabelCreated,
    LabelDeleted,
    LabelUpdated,
    TaskArchived,
    TaskCreated,
    TaskDatesChanged,
    TaskDeleted,
    TaskDuplicated,
    TaskParentChanged,
    TaskPriorityChanged,
    TaskReordered,
    TaskRestored,
    TaskStatusChanged,
    TaskUpdated,
)
from app.tasks.domain.exceptions import (
    InvalidDateRangeError,
    InvalidTaskStatusTransitionError,
    TaskAlreadyArchivedError,
    TaskAlreadyDeletedError,
    TaskCannotBeOwnParentError,
    TaskNotArchivedError,
)
from app.tasks.domain.workflow import TERMINAL_STATUSES, TaskPriority, TaskStatus, Workflow

# Fractional-indexing gap for the initial/append position — halving this
# gap on each insert-between is what lets drag-and-drop reordering avoid
# rewriting every sibling row's position.
_POSITION_GAP = 1024.0


def compute_position_between(previous: float | None, following: float | None) -> float:
    if previous is None and following is None:
        return _POSITION_GAP
    if previous is None:
        return following - _POSITION_GAP  # type: ignore[operator]
    if following is None:
        return previous + _POSITION_GAP
    return (previous + following) / 2


class Task(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        project_id: EntityId,
        org_id: OrgId,
        title: str,
        description: str,
        status: TaskStatus,
        priority: TaskPriority,
        parent_task_id: EntityId | None = None,
        position: float = 0.0,
        start_date: datetime | None = None,
        due_date: datetime | None = None,
        reminder_date: datetime | None = None,
        completion_date: datetime | None = None,
        is_archived: bool = False,
        archived_at: datetime | None = None,
        deleted_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.project_id = project_id
        self.org_id = org_id
        self.title = title
        self.description = description
        self.status = status
        self.priority = priority
        self.parent_task_id = parent_task_id
        self.position = position
        self.start_date = start_date
        self.due_date = due_date
        self.reminder_date = reminder_date
        self.completion_date = completion_date
        self.is_archived = is_archived
        self.archived_at = archived_at
        self.deleted_at = deleted_at
        self.version = version

    @classmethod
    def create(
        cls,
        *,
        project_id: EntityId,
        org_id: OrgId,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        initial_status: TaskStatus = TaskStatus.BACKLOG,
        parent_task_id: EntityId | None = None,
        position: float = _POSITION_GAP,
        start_date: datetime | None = None,
        due_date: datetime | None = None,
        reminder_date: datetime | None = None,
    ) -> "Task":
        _assert_date_order(start_date, due_date)
        task = cls(
            id=EntityId(new_uuid7()), project_id=project_id, org_id=org_id, title=title, description=description,
            status=initial_status, priority=priority, parent_task_id=parent_task_id, position=position,
            start_date=start_date, due_date=due_date, reminder_date=reminder_date,
        )
        task.record_event(TaskCreated(aggregate_id=task.id, project_id=project_id, org_id=org_id, title=title))
        return task

    @classmethod
    def duplicate_from(cls, source: "Task", *, title: str | None = None) -> "Task":
        """Copies title/description/priority/labels-agnostic fields from an
        existing task into a brand-new one — always starts fresh at the
        workflow's initial status (Backlog), never carries over
        assignments/dates/position, matching how most PM tools treat
        "duplicate" (a template-like copy, not a clone of in-flight state)."""
        duplicate = cls.create(
            project_id=source.project_id, org_id=source.org_id, title=title or f"{source.title} (copy)",
            description=source.description, priority=source.priority, parent_task_id=source.parent_task_id,
        )
        duplicate.pull_domain_events()  # discard the TaskCreated just recorded by .create()
        duplicate.record_event(
            TaskDuplicated(aggregate_id=duplicate.id, project_id=source.project_id, org_id=source.org_id, source_task_id=source.id)
        )
        return duplicate

    def assert_not_deleted(self) -> None:
        if self.deleted_at is not None:
            raise TaskAlreadyDeletedError()

    def update(self, *, title: str | None = None, description: str | None = None) -> None:
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        self.record_event(TaskUpdated(aggregate_id=self.id))

    def change_status(self, target_status: TaskStatus, *, workflow: Workflow) -> None:
        if target_status == self.status:
            return
        if not workflow.is_valid_transition(self.status, target_status):
            raise InvalidTaskStatusTransitionError(self.status.value, target_status.value)
        previous_status = self.status
        self.status = target_status
        self.completion_date = utcnow() if target_status == TaskStatus.DONE else None
        self.record_event(TaskStatusChanged(aggregate_id=self.id, from_status=previous_status.value, to_status=target_status.value))

    def change_priority(self, priority: TaskPriority) -> None:
        self.priority = priority
        self.record_event(TaskPriorityChanged(aggregate_id=self.id, priority=priority.value))

    def set_dates(
        self, *, start_date: datetime | None = None, due_date: datetime | None = None, reminder_date: datetime | None = None,
    ) -> None:
        new_start = start_date if start_date is not None else self.start_date
        new_due = due_date if due_date is not None else self.due_date
        _assert_date_order(new_start, new_due)
        self.start_date = new_start
        self.due_date = new_due
        if reminder_date is not None:
            self.reminder_date = reminder_date
        self.record_event(TaskDatesChanged(aggregate_id=self.id))

    def is_overdue(self, *, now: datetime | None = None) -> bool:
        if self.due_date is None or self.status in TERMINAL_STATUSES:
            return False
        return self.due_date < (now or utcnow())

    def set_position(self, position: float) -> None:
        self.position = position
        self.record_event(TaskReordered(aggregate_id=self.id, position=position))

    def set_parent(self, parent_task_id: EntityId | None) -> None:
        if parent_task_id is not None and parent_task_id == self.id:
            raise TaskCannotBeOwnParentError()
        self.parent_task_id = parent_task_id
        self.record_event(TaskParentChanged(aggregate_id=self.id, parent_task_id=parent_task_id))

    def archive(self) -> None:
        if self.is_archived:
            raise TaskAlreadyArchivedError()
        self.is_archived = True
        self.archived_at = utcnow()
        self.record_event(TaskArchived(aggregate_id=self.id))

    def restore(self) -> None:
        if not self.is_archived:
            raise TaskNotArchivedError()
        self.is_archived = False
        self.archived_at = None
        self.record_event(TaskRestored(aggregate_id=self.id))

    def mark_deleted(self) -> None:
        self.assert_not_deleted()
        self.deleted_at = utcnow()
        self.record_event(TaskDeleted(aggregate_id=self.id))


def _assert_date_order(start_date: datetime | None, due_date: datetime | None) -> None:
    if start_date is not None and due_date is not None and start_date > due_date:
        raise InvalidDateRangeError("start_date must not be after due_date")


class TaskAssignment:
    """Hard-deletable join entity — same convention as every other
    membership-shaped join across the platform."""

    def __init__(
        self, *, id: EntityId, task_id: EntityId, user_id: UserId, assigned_by: UserId, is_primary: bool = False,
        assigned_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.task_id = task_id
        self.user_id = user_id
        self.assigned_by = assigned_by
        self.is_primary = is_primary
        self.assigned_at = assigned_at or utcnow()

    @classmethod
    def create(cls, *, task_id: EntityId, user_id: UserId, assigned_by: UserId, is_primary: bool = False) -> "TaskAssignment":
        return cls(id=EntityId(new_uuid7()), task_id=task_id, user_id=user_id, assigned_by=assigned_by, is_primary=is_primary)


class TaskAssignmentAction:
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    REASSIGNED = "reassigned"


class TaskAssignmentHistoryRecord:
    """Append-only — no update/delete, per the platform-wide convention for
    historical records (Identity's PasswordHistoryEntry, AuditLogRecord)."""

    def __init__(
        self, *, id: EntityId, task_id: EntityId, user_id: UserId, action: str, actor_user_id: UserId,
        occurred_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.task_id = task_id
        self.user_id = user_id
        self.action = action
        self.actor_user_id = actor_user_id
        self.occurred_at = occurred_at or utcnow()

    @classmethod
    def create(cls, *, task_id: EntityId, user_id: UserId, action: str, actor_user_id: UserId) -> "TaskAssignmentHistoryRecord":
        return cls(id=EntityId(new_uuid7()), task_id=task_id, user_id=user_id, action=action, actor_user_id=actor_user_id)


class Label(EventRecordingMixin):
    def __init__(
        self, *, id: EntityId, project_id: EntityId, name: str, color: str, version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.project_id = project_id
        self.name = name
        self.color = color
        self.version = version

    @classmethod
    def create(cls, *, project_id: EntityId, name: str, color: str) -> "Label":
        label = cls(id=EntityId(new_uuid7()), project_id=project_id, name=name, color=color)
        label.record_event(LabelCreated(aggregate_id=label.id, project_id=project_id, name=name))
        return label

    def update(self, *, name: str | None = None, color: str | None = None) -> None:
        if name is not None:
            self.name = name
        if color is not None:
            self.color = color
        self.record_event(LabelUpdated(aggregate_id=self.id))

    def mark_deleted(self) -> None:
        self.record_event(LabelDeleted(aggregate_id=self.id))


class TaskLabel:
    """Hard-deletable join entity."""

    def __init__(self, *, id: EntityId, task_id: EntityId, label_id: EntityId) -> None:
        self.id = id
        self.task_id = task_id
        self.label_id = label_id

    @classmethod
    def create(cls, *, task_id: EntityId, label_id: EntityId) -> "TaskLabel":
        return cls(id=EntityId(new_uuid7()), task_id=task_id, label_id=label_id)


class TaskDependency:
    """Directed edge: `task_id` is blocked by (depends on) `depends_on_task_id`.
    Hard-deletable join entity; cycle prevention happens at the application
    layer (needs to walk sibling aggregates, same as Identity's Role/Team
    hierarchy cycle checks)."""

    def __init__(self, *, id: EntityId, task_id: EntityId, depends_on_task_id: EntityId, created_at: datetime | None = None) -> None:
        self.id = id
        self.task_id = task_id
        self.depends_on_task_id = depends_on_task_id
        self.created_at = created_at or utcnow()

    @classmethod
    def create(cls, *, task_id: EntityId, depends_on_task_id: EntityId) -> "TaskDependency":
        return cls(id=EntityId(new_uuid7()), task_id=task_id, depends_on_task_id=depends_on_task_id)


class TaskRelation:
    """Symmetric, non-blocking "related task" link — no cycle concern,
    since it carries no hierarchy or ordering semantics."""

    def __init__(self, *, id: EntityId, task_id: EntityId, related_task_id: EntityId, created_at: datetime | None = None) -> None:
        self.id = id
        self.task_id = task_id
        self.related_task_id = related_task_id
        self.created_at = created_at or utcnow()

    @classmethod
    def create(cls, *, task_id: EntityId, related_task_id: EntityId) -> "TaskRelation":
        return cls(id=EntityId(new_uuid7()), task_id=task_id, related_task_id=related_task_id)
