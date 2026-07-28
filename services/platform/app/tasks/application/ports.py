"""
Application-layer ports: the only way this bounded context is allowed to
reach Identity or Projects & Workspaces (ADR-005..009's cross-context
dependency rule — forbidden except through an Event Bus or an explicit
Anti-Corruption Layer). Mirrors app.projects.application.ports exactly.

- OrgPermissionCheckerPort is satisfied structurally, no adapter class
  needed, by Identity's real PermissionEvaluator instance.
- ProjectContextPort *does* need a real adapter (infrastructure/
  projects_adapter.py), since it wraps Projects' own ProjectService/
  ProjectMembershipService (public application-layer services, not
  infrastructure) and translates their DTOs into this context's own
  ProjectSummary/ProjectMemberSummary — never modifying Projects itself.
- TasksUnitOfWorkPort mirrors Identity's/Projects' UnitOfWork ports exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.platform_core.events.publisher import OutboxWriter
from app.tasks.domain.repositories import (
    LabelRepository,
    TaskAssignmentHistoryRepository,
    TaskAssignmentRepository,
    TaskDependencyRepository,
    TaskLabelRepository,
    TaskRelationRepository,
    TaskRepository,
    TasksAuditLogRepository,
    WorkflowDefinitionRepository,
)


class TasksUnitOfWorkPort(Protocol):
    tasks: TaskRepository
    task_assignments: TaskAssignmentRepository
    task_assignment_history: TaskAssignmentHistoryRepository
    labels: LabelRepository
    task_labels: TaskLabelRepository
    task_dependencies: TaskDependencyRepository
    task_relations: TaskRelationRepository
    workflow_definitions: WorkflowDefinitionRepository
    audit_logs: TasksAuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "TasksUnitOfWorkPort": ...

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
class UserSummary:
    id: UUID
    email: str
    display_name: str


class UserDirectoryPort(Protocol):
    """Satisfied, structurally, by reusing Projects & Workspaces'
    IdentityUserDirectoryAdapter directly (composition.py) — that class
    already wraps Identity's UserRepository via IdentityModule's public
    create_unit_of_work() seam and returns exactly this shape, so Tasks
    doesn't need a third near-identical adapter to reach the same data."""

    async def get_by_id(self, *, user_id: UUID) -> UserSummary | None: ...
