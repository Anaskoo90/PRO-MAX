"""
Application-layer ports: the only way this bounded context is allowed to
reach Identity, Projects & Workspaces, or Tasks & Work Management
(ADR-005..009's cross-context dependency rule — forbidden except through
an Event Bus or an explicit Anti-Corruption Layer). Mirrors every prior
context's application/ports.py exactly.

- OrgPermissionCheckerPort is satisfied structurally, no adapter class
  needed, by Identity's real PermissionEvaluator instance.
- ProjectContextPort *does* need a real adapter (infrastructure/
  projects_adapter.py) — Boards builds its own, mirroring Tasks' identical
  adapter, rather than importing Tasks' (each context owns its own ACL to
  Projects; that's the expected shape, not duplication to avoid).
- TasksContextPort *does* need a real adapter (infrastructure/
  tasks_adapter.py), wrapping Tasks' own public application services
  (TaskService, TaskLifecycleService, TaskAssignmentService, LabelService —
  all public attributes on TasksModule, never Tasks' infrastructure).
- BoardsUnitOfWorkPort mirrors every prior context's UnitOfWork port exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.platform_core.events.publisher import OutboxWriter
from app.boards.domain.repositories import (
    BoardCardRepository,
    BoardColumnRepository,
    BoardRepository,
    BoardsAuditLogRepository,
    SprintBurndownSnapshotRepository,
    SprintRepository,
    SwimlaneRepository,
)


class BoardsUnitOfWorkPort(Protocol):
    boards: BoardRepository
    board_columns: BoardColumnRepository
    swimlanes: SwimlaneRepository
    board_cards: BoardCardRepository
    sprints: SprintRepository
    sprint_burndown_snapshots: SprintBurndownSnapshotRepository
    audit_logs: BoardsAuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "BoardsUnitOfWorkPort": ...

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


class TaskStatusRejectedError(Exception):
    """Raised by TasksContextPort.change_task_status when the underlying
    Tasks context rejects the transition (e.g. the target status isn't
    valid under that task's configured workflow) — Boards surfaces this as
    a board-level error rather than letting Tasks' own exception type leak
    across the context boundary."""


class TasksContextPort(Protocol):
    async def get_task(self, *, task_id: UUID) -> TaskSummary | None: ...

    async def list_tasks_for_project(self, *, project_id: UUID, include_archived: bool = False) -> list[TaskSummary]: ...

    async def change_task_status(self, *, task_id: UUID, actor_user_id: UUID, status: str) -> None: ...

    async def list_assignee_ids(self, *, task_id: UUID) -> list[UUID]: ...

    async def list_label_ids(self, *, task_id: UUID) -> list[UUID]: ...
