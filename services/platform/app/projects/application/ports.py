"""
Application-layer ports: the only way this bounded context is allowed to
reach Identity (ADR-005..009's cross-context dependency rule — forbidden
except through an Event Bus or an explicit Anti-Corruption Layer).

- OrgPermissionCheckerPort is satisfied *structurally, with no adapter
  class needed* by app.identity.application.rbac_engine.PermissionEvaluator
  — its `has_permission(*, user_id, org_id, resource, action) -> bool`
  signature already matches exactly. composition.py passes Identity's real
  PermissionEvaluator instance wherever this Port is expected.
- UserDirectoryPort *does* need a real adapter (identity_adapter.py),
  since Identity's UserRepository returns Identity's own User entity —
  translating that into this context's own UserSummary is the ACL's job.
- ProjectsUnitOfWorkPort mirrors Identity's IdentityUnitOfWorkPort exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.platform_core.events.publisher import OutboxWriter
from app.projects.domain.repositories import (
    ProjectMembershipRepository,
    ProjectRepository,
    ProjectsAuditLogRepository,
    ProjectTemplateRepository,
    WorkspaceMembershipRepository,
    WorkspaceRepository,
)


class ProjectsUnitOfWorkPort(Protocol):
    workspaces: WorkspaceRepository
    workspace_memberships: WorkspaceMembershipRepository
    projects: ProjectRepository
    project_memberships: ProjectMembershipRepository
    project_templates: ProjectTemplateRepository
    audit_logs: ProjectsAuditLogRepository
    outbox: OutboxWriter

    async def __aenter__(self) -> "ProjectsUnitOfWorkPort": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class OrgPermissionCheckerPort(Protocol):
    async def has_permission(self, *, user_id: UUID, org_id: UUID, resource: str, action: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class UserSummary:
    id: UUID
    email: str
    display_name: str


class UserDirectoryPort(Protocol):
    async def find_by_email(self, *, org_id: UUID, email: str) -> UserSummary | None: ...

    async def get_by_id(self, *, user_id: UUID) -> UserSummary | None: ...
