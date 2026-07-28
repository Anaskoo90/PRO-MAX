"""
Application-layer ports: the only way this bounded context is allowed to
reach Identity, Projects & Workspaces, Tasks & Work Management, or Boards &
Agile Management (ADR-005..009's cross-context dependency rule — forbidden
except through an Event Bus or an explicit Anti-Corruption Layer). Mirrors
every prior context's application/ports.py exactly.

- OrgPermissionCheckerPort is satisfied structurally, no adapter class
  needed, by Identity's real PermissionEvaluator instance.
- ProjectContextPort needs a real adapter (infrastructure/projects_adapter.py)
  — Workflow Engine builds its own, mirroring Boards'/Tasks' identical
  adapter (each context owns its own ACL to Projects).
- TasksContextPort needs a real adapter (infrastructure/tasks_adapter.py),
  wrapping Tasks' own public application services.
- BoardsContextPort needs a real adapter (infrastructure/boards_adapter.py),
  wrapping Boards' own public application services — used only to evaluate
  the BOARD/SPRINT workflow conditions.
- WebhookExecutorPort is satisfied by an httpx-based infrastructure
  implementation (infrastructure/webhook_executor.py) — the EXECUTE_WEBHOOK
  action.
- WorkflowEngineUnitOfWorkPort mirrors every prior context's UnitOfWork
  port exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.platform_core.events.publisher import OutboxWriter
from app.workflow_engine.domain.repositories import (
    PendingAutomationActionRepository,
    TransitionRuleRepository,
    WorkflowActionRepository,
    WorkflowApprovalRequestRepository,
    WorkflowAuditLogRepository,
    WorkflowChecklistCompletionRepository,
    WorkflowChecklistItemRepository,
    WorkflowConditionRepository,
    WorkflowActivityEntryRepository,
    WorkflowRepository,
    WorkflowExecutionRecordRepository,
    WorkflowStateRepository,
    WorkflowTaskStateRepository,
    WorkflowTransitionRepository,
)


class WorkflowEngineUnitOfWorkPort(Protocol):
    workflows: WorkflowRepository
    states: WorkflowStateRepository
    transitions: WorkflowTransitionRepository
    rules: TransitionRuleRepository
    actions: WorkflowActionRepository
    conditions: WorkflowConditionRepository
    task_states: WorkflowTaskStateRepository
    execution_records: WorkflowExecutionRecordRepository
    pending_actions: PendingAutomationActionRepository
    approvals: WorkflowApprovalRequestRepository
    checklist_items: WorkflowChecklistItemRepository
    checklist_completions: WorkflowChecklistCompletionRepository
    activity_entries: WorkflowActivityEntryRepository
    audit_logs: WorkflowAuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "WorkflowEngineUnitOfWorkPort": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class OrgPermissionCheckerPort(Protocol):
    async def has_permission(self, *, user_id: UUID, org_id: UUID, resource: str, action: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    id: UUID
    org_id: UUID
    workspace_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class ProjectMemberSummary:
    user_id: UUID
    role: str
    status: str


class ProjectContextPort(Protocol):
    async def get_project(self, *, project_id: UUID) -> ProjectSummary | None: ...

    async def get_member(self, *, project_id: UUID, user_id: UUID) -> ProjectMemberSummary | None: ...

    async def list_members(self, *, project_id: UUID) -> list[ProjectMemberSummary]: ...


@dataclass(frozen=True, slots=True)
class TaskSummary:
    id: UUID
    project_id: UUID
    org_id: UUID
    title: str
    status: str
    priority: str
    assignee_ids: tuple[UUID, ...]
    label_ids: tuple[UUID, ...]


class TaskStatusRejectedError(Exception):
    """Raised by TasksContextPort.change_task_status when the underlying
    Tasks context rejects the transition — Workflow Engine surfaces this as
    its own error rather than letting Tasks' exception type leak across
    the context boundary."""


class TasksContextPort(Protocol):
    async def get_task(self, *, task_id: UUID) -> TaskSummary | None: ...

    async def change_task_status(self, *, task_id: UUID, actor_user_id: UUID, status: str) -> None: ...

    async def change_priority(self, *, task_id: UUID, actor_user_id: UUID, priority: str) -> None: ...

    async def set_due_date(self, *, task_id: UUID, actor_user_id: UUID, due_date) -> None: ...

    async def assign_user(self, *, task_id: UUID, actor_user_id: UUID, assignee_user_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class BoardPlacementSummary:
    board_id: UUID
    column_id: UUID | None
    sprint_id: UUID | None


class BoardsContextPort(Protocol):
    async def get_board_placement_for_task(self, *, project_id: UUID, task_id: UUID) -> BoardPlacementSummary | None: ...


@dataclass(frozen=True, slots=True)
class UserSummary:
    id: UUID
    email: str
    display_name: str


class UserDirectoryPort(Protocol):
    async def get_by_id(self, *, user_id: UUID) -> UserSummary | None: ...


class WebhookExecutorPort(Protocol):
    async def execute(self, *, url: str, payload: dict[str, Any]) -> None: ...
