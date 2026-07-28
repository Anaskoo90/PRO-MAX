"""In-memory fakes satisfying the Workflow Engine repository Protocols and
application ports — mirrors tests/boards/unit/fakes.py exactly."""

from __future__ import annotations

from datetime import datetime

from app.workflow_engine.application.ports import (
    BoardPlacementSummary,
    ProjectMemberSummary,
    ProjectSummary,
    TaskStatusRejectedError,
    TaskSummary,
    UserSummary,
)
from app.workflow_engine.domain.entities import (
    PendingActionStatus,
    PendingAutomationAction,
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
)
from app.platform_core.shared_kernel.types import EntityId


class FakeWorkflowRepository:
    def __init__(self) -> None:
        self.workflows: dict[EntityId, WorkflowDefinition] = {}

    async def get_by_id(self, workflow_id: EntityId) -> WorkflowDefinition | None:
        w = self.workflows.get(workflow_id)
        return w if w and w.deleted_at is None else None

    async def list_for_project(self, project_id: EntityId, *, include_archived: bool = False) -> list[WorkflowDefinition]:
        return [
            w for w in self.workflows.values()
            if w.project_id == project_id and w.deleted_at is None and (include_archived or w.status.value != "archived")
        ]

    async def add(self, workflow: WorkflowDefinition) -> None:
        self.workflows[workflow.id] = workflow

    async def update(self, workflow: WorkflowDefinition) -> None:
        self.workflows[workflow.id] = workflow


class FakeWorkflowStateRepository:
    def __init__(self) -> None:
        self.states: dict[EntityId, WorkflowState] = {}

    async def get_by_id(self, state_id: EntityId) -> WorkflowState | None:
        return self.states.get(state_id)

    async def get_by_name(self, workflow_id: EntityId, name: str) -> WorkflowState | None:
        return next((s for s in self.states.values() if s.workflow_id == workflow_id and s.name == name), None)

    async def get_initial(self, workflow_id: EntityId) -> WorkflowState | None:
        return next((s for s in self.states.values() if s.workflow_id == workflow_id and s.is_initial), None)

    async def list_for_workflow(self, workflow_id: EntityId) -> list[WorkflowState]:
        return sorted((s for s in self.states.values() if s.workflow_id == workflow_id), key=lambda s: s.position)

    async def add(self, state: WorkflowState) -> None:
        self.states[state.id] = state

    async def update(self, state: WorkflowState) -> None:
        self.states[state.id] = state

    async def delete(self, state_id: EntityId) -> None:
        self.states.pop(state_id, None)


class FakeWorkflowTransitionRepository:
    def __init__(self) -> None:
        self.transitions: dict[EntityId, WorkflowTransition] = {}

    async def get_by_id(self, transition_id: EntityId) -> WorkflowTransition | None:
        return self.transitions.get(transition_id)

    async def list_for_workflow(self, workflow_id: EntityId) -> list[WorkflowTransition]:
        return sorted((t for t in self.transitions.values() if t.workflow_id == workflow_id), key=lambda t: t.position)

    async def list_from_state(self, from_state_id: EntityId) -> list[WorkflowTransition]:
        return [t for t in self.transitions.values() if t.from_state_id == from_state_id]

    async def references_state(self, state_id: EntityId) -> bool:
        return any(t.from_state_id == state_id or t.to_state_id == state_id for t in self.transitions.values())

    async def add(self, transition: WorkflowTransition) -> None:
        self.transitions[transition.id] = transition

    async def update(self, transition: WorkflowTransition) -> None:
        self.transitions[transition.id] = transition

    async def delete(self, transition_id: EntityId) -> None:
        self.transitions.pop(transition_id, None)


class FakeTransitionRuleRepository:
    def __init__(self) -> None:
        self.rules: dict[EntityId, TransitionRule] = {}

    async def get_by_id(self, rule_id: EntityId) -> TransitionRule | None:
        return self.rules.get(rule_id)

    async def list_for_transition(self, transition_id: EntityId) -> list[TransitionRule]:
        return [r for r in self.rules.values() if r.transition_id == transition_id]

    async def add(self, rule: TransitionRule) -> None:
        self.rules[rule.id] = rule

    async def delete(self, rule_id: EntityId) -> None:
        self.rules.pop(rule_id, None)


class FakeWorkflowActionRepository:
    def __init__(self) -> None:
        self.actions: dict[EntityId, WorkflowAction] = {}

    async def get_by_id(self, action_id: EntityId) -> WorkflowAction | None:
        return self.actions.get(action_id)

    async def list_for_transition(self, transition_id: EntityId) -> list[WorkflowAction]:
        return sorted((a for a in self.actions.values() if a.transition_id == transition_id), key=lambda a: a.position)

    async def add(self, action: WorkflowAction) -> None:
        self.actions[action.id] = action

    async def delete(self, action_id: EntityId) -> None:
        self.actions.pop(action_id, None)


class FakeWorkflowConditionRepository:
    def __init__(self) -> None:
        self.conditions: dict[EntityId, WorkflowCondition] = {}

    async def get_by_id(self, condition_id: EntityId) -> WorkflowCondition | None:
        return self.conditions.get(condition_id)

    async def list_for_transition(self, transition_id: EntityId) -> list[WorkflowCondition]:
        return sorted((c for c in self.conditions.values() if c.transition_id == transition_id), key=lambda c: c.position)

    async def add(self, condition: WorkflowCondition) -> None:
        self.conditions[condition.id] = condition

    async def delete(self, condition_id: EntityId) -> None:
        self.conditions.pop(condition_id, None)


class FakeWorkflowTaskStateRepository:
    def __init__(self) -> None:
        self.task_states: dict[EntityId, WorkflowTaskState] = {}

    async def get(self, workflow_id: EntityId, task_id: EntityId) -> WorkflowTaskState | None:
        return next((s for s in self.task_states.values() if s.workflow_id == workflow_id and s.task_id == task_id), None)

    async def list_for_task(self, task_id: EntityId) -> list[WorkflowTaskState]:
        return [s for s in self.task_states.values() if s.task_id == task_id]

    async def add(self, task_state: WorkflowTaskState) -> None:
        self.task_states[task_state.id] = task_state

    async def update(self, task_state: WorkflowTaskState) -> None:
        self.task_states[task_state.id] = task_state


class FakeWorkflowExecutionRecordRepository:
    def __init__(self) -> None:
        self.records: list[WorkflowExecutionRecord] = []

    async def add(self, record: WorkflowExecutionRecord) -> None:
        self.records.append(record)

    async def list_for_task(self, workflow_id: EntityId, task_id: EntityId) -> list[WorkflowExecutionRecord]:
        return [r for r in self.records if r.workflow_id == workflow_id and r.task_id == task_id]


class FakePendingAutomationActionRepository:
    def __init__(self) -> None:
        self.pending: dict[EntityId, PendingAutomationAction] = {}

    async def get_by_id(self, pending_action_id: EntityId) -> PendingAutomationAction | None:
        return self.pending.get(pending_action_id)

    async def list_due(self, *, before: datetime, status: PendingActionStatus = PendingActionStatus.PENDING) -> list[PendingAutomationAction]:
        return [p for p in self.pending.values() if p.run_at <= before and p.status == status]

    async def add(self, pending_action: PendingAutomationAction) -> None:
        self.pending[pending_action.id] = pending_action

    async def update(self, pending_action: PendingAutomationAction) -> None:
        self.pending[pending_action.id] = pending_action


class FakeWorkflowApprovalRequestRepository:
    def __init__(self) -> None:
        self.approvals: dict[EntityId, WorkflowApprovalRequest] = {}

    async def get_by_id(self, approval_id: EntityId) -> WorkflowApprovalRequest | None:
        return self.approvals.get(approval_id)

    async def get_latest_for_task(self, transition_id: EntityId, task_id: EntityId) -> WorkflowApprovalRequest | None:
        matches = sorted(
            (a for a in self.approvals.values() if a.transition_id == transition_id and a.task_id == task_id),
            key=lambda a: a.requested_at, reverse=True,
        )
        return matches[0] if matches else None

    async def add(self, approval: WorkflowApprovalRequest) -> None:
        self.approvals[approval.id] = approval

    async def update(self, approval: WorkflowApprovalRequest) -> None:
        self.approvals[approval.id] = approval


class FakeWorkflowChecklistItemRepository:
    def __init__(self) -> None:
        self.items: dict[EntityId, WorkflowChecklistItem] = {}

    async def get_by_id(self, item_id: EntityId) -> WorkflowChecklistItem | None:
        return self.items.get(item_id)

    async def list_for_transition(self, transition_id: EntityId) -> list[WorkflowChecklistItem]:
        return sorted((i for i in self.items.values() if i.transition_id == transition_id), key=lambda i: i.position)

    async def add(self, item: WorkflowChecklistItem) -> None:
        self.items[item.id] = item

    async def update(self, item: WorkflowChecklistItem) -> None:
        self.items[item.id] = item

    async def delete(self, item_id: EntityId) -> None:
        self.items.pop(item_id, None)


class FakeWorkflowChecklistCompletionRepository:
    def __init__(self) -> None:
        self.completions: list[WorkflowChecklistCompletion] = []

    async def get(self, checklist_item_id: EntityId, task_id: EntityId) -> WorkflowChecklistCompletion | None:
        return next((c for c in self.completions if c.checklist_item_id == checklist_item_id and c.task_id == task_id), None)

    async def list_for_task(self, transition_id: EntityId, task_id: EntityId) -> list[WorkflowChecklistCompletion]:
        return [c for c in self.completions if c.task_id == task_id]

    async def add(self, completion: WorkflowChecklistCompletion) -> None:
        self.completions.append(completion)


class FakeWorkflowActivityEntryRepository:
    def __init__(self) -> None:
        self.entries: list[WorkflowActivityEntry] = []

    async def add(self, entry: WorkflowActivityEntry) -> None:
        self.entries.append(entry)

    async def list_for_task(self, workflow_id: EntityId, task_id: EntityId) -> list[WorkflowActivityEntry]:
        return [e for e in self.entries if e.workflow_id == workflow_id and e.task_id == task_id]


class FakeWorkflowAuditLogRepository:
    def __init__(self) -> None:
        self.records: list = []

    async def add(self, record) -> None:
        self.records.append(record)

    async def list_for_org(self, org_id, *, category=None, limit: int = 50):
        results = [r for r in self.records if r.org_id == org_id]
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:limit]


class FakeOutboxWriter:
    async def append(self, event) -> None:
        pass


class FakeWorkflowEngineUnitOfWork:
    def __init__(self) -> None:
        self.workflows = FakeWorkflowRepository()
        self.states = FakeWorkflowStateRepository()
        self.transitions = FakeWorkflowTransitionRepository()
        self.rules = FakeTransitionRuleRepository()
        self.actions = FakeWorkflowActionRepository()
        self.conditions = FakeWorkflowConditionRepository()
        self.task_states = FakeWorkflowTaskStateRepository()
        self.execution_records = FakeWorkflowExecutionRecordRepository()
        self.pending_actions = FakePendingAutomationActionRepository()
        self.approvals = FakeWorkflowApprovalRequestRepository()
        self.checklist_items = FakeWorkflowChecklistItemRepository()
        self.checklist_completions = FakeWorkflowChecklistCompletionRepository()
        self.activity_entries = FakeWorkflowActivityEntryRepository()
        self.audit_logs = FakeWorkflowAuditLogRepository()
        self.outbox = FakeOutboxWriter()

    async def __aenter__(self) -> "FakeWorkflowEngineUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class AllowAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return True


class DenyAllPermissionChecker:
    async def has_permission(self, *, user_id, org_id, resource: str, action: str) -> bool:
        return False


class FakeProjectContext:
    """Fakes ProjectContextPort — the ACL boundary to Projects & Workspaces."""

    def __init__(self, *, project: ProjectSummary, members: list[ProjectMemberSummary] | None = None) -> None:
        self.project = project
        self.members = members or []

    async def get_project(self, *, project_id) -> ProjectSummary | None:
        return self.project if self.project.id == project_id else None

    async def get_member(self, *, project_id, user_id) -> ProjectMemberSummary | None:
        if project_id != self.project.id:
            return None
        return next((m for m in self.members if m.user_id == user_id), None)

    async def list_members(self, *, project_id) -> list[ProjectMemberSummary]:
        return list(self.members) if project_id == self.project.id else []


class FakeTasksContext:
    """Fakes TasksContextPort — the ACL boundary to Tasks & Work Management."""

    def __init__(self, *, tasks: list[TaskSummary] | None = None, reject_statuses: set[str] | None = None) -> None:
        self.tasks_by_id = {t.id: t for t in (tasks or [])}
        self._reject_statuses = reject_statuses or set()
        self.priority_changes: list[tuple] = []
        self.due_date_changes: list[tuple] = []
        self.assignments: list[tuple] = []
        self.status_changes: list[tuple] = []

    async def get_task(self, *, task_id) -> TaskSummary | None:
        return self.tasks_by_id.get(task_id)

    async def change_task_status(self, *, task_id, actor_user_id, status: str) -> None:
        if status in self._reject_statuses:
            raise TaskStatusRejectedError(f"'{status}' rejected by Tasks")
        self.status_changes.append((task_id, status))
        existing = self.tasks_by_id.get(task_id)
        if existing is not None:
            self.tasks_by_id[task_id] = TaskSummary(
                id=existing.id, project_id=existing.project_id, org_id=existing.org_id, title=existing.title,
                status=status, priority=existing.priority, assignee_ids=existing.assignee_ids, label_ids=existing.label_ids,
            )

    async def change_priority(self, *, task_id, actor_user_id, priority: str) -> None:
        self.priority_changes.append((task_id, priority))

    async def set_due_date(self, *, task_id, actor_user_id, due_date) -> None:
        self.due_date_changes.append((task_id, due_date))

    async def assign_user(self, *, task_id, actor_user_id, assignee_user_id) -> None:
        self.assignments.append((task_id, assignee_user_id))


class FakeBoardsContext:
    """Fakes BoardsContextPort — the ACL boundary to Boards & Agile Management."""

    def __init__(self, *, placements: dict[EntityId, BoardPlacementSummary] | None = None) -> None:
        self.placements = placements or {}

    async def get_board_placement_for_task(self, *, project_id, task_id) -> BoardPlacementSummary | None:
        return self.placements.get(task_id)


class FakeUserDirectory:
    def __init__(self, users: dict | None = None) -> None:
        self.by_id = users or {}

    async def get_by_id(self, *, user_id) -> UserSummary | None:
        return self.by_id.get(user_id)


class FakeWebhookExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def execute(self, *, url: str, payload: dict) -> None:
        self.calls.append((url, payload))
