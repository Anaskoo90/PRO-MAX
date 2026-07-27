"""
Projects & Workspaces domain entities.

Two distinct authorization concepts, deliberately not conflated:

- Workspace/Project membership roles (WorkspaceRole, ProjectRole below) are
  *local, instance-scoped* — "is this specific user an owner of this
  specific project" — and are this bounded context's own concern.
- Organization-wide capability checks ("can this user create a workspace
  at all") are delegated to Identity's existing RBAC engine via
  application.ports.OrgPermissionCheckerPort, not reimplemented here.

Plain Python classes, not pydantic/SQLAlchemy models — same dependency
rule as Identity (ADR-005..009): domain depends only on shared_kernel/events.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow

from app.projects.domain.events import (
    ProjectArchived,
    ProjectCreated,
    ProjectDeleted,
    ProjectStatusChanged,
    ProjectTemplateCreated,
    ProjectTemplateDeleted,
    ProjectTemplateImported,
    ProjectTemplateUpdated,
    ProjectUnarchived,
    ProjectUpdated,
    ProjectVisibilityChanged,
    WorkspaceArchived,
    WorkspaceCreated,
    WorkspaceReactivated,
    WorkspaceUpdated,
)
from app.projects.domain.exceptions import (
    InvalidProjectStatusTransitionError,
    InvalidWorkspaceSlugError,
    ProjectAlreadyDeletedError,
    WorkspaceNotActiveError,
)

# Identical pattern to Identity's Organization slug validation
# (app.identity.domain.organization) — same rules, same rationale, kept as
# a separate constant here rather than importing Identity's private regex,
# since "never modify Identity" for this pass also means not creating a new
# cross-context dependency on one of its internals.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{1,48}[a-z0-9])?$")


def _validate_slug(slug: str) -> str:
    if not _SLUG_PATTERN.match(slug):
        raise InvalidWorkspaceSlugError(slug)
    return slug


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class ProjectStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


_ALLOWED_PROJECT_STATUS_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.PLANNING: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD, ProjectStatus.ARCHIVED}),
    ProjectStatus.ACTIVE: frozenset({ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}),
    ProjectStatus.ON_HOLD: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
    ProjectStatus.COMPLETED: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
    ProjectStatus.ARCHIVED: frozenset({ProjectStatus.ACTIVE}),
}


class ProjectVisibility(StrEnum):
    PRIVATE = "private"  # only explicit ProjectMembership rows can see it
    WORKSPACE = "workspace"  # every workspace member can see it
    ORGANIZATION = "organization"  # every organization member can see it


class ProjectRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"


class Workspace(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        name: str,
        slug: str,
        description: str,
        status: WorkspaceStatus,
        settings: dict[str, Any] | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.name = name
        self.slug = _validate_slug(slug)
        self.description = description
        self.status = status
        self.settings = settings or {}
        self.version = version

    @classmethod
    def create(cls, *, org_id: OrgId, name: str, slug: str, description: str = "") -> "Workspace":
        workspace = cls(
            id=EntityId(new_uuid7()), org_id=org_id, name=name, slug=slug, description=description,
            status=WorkspaceStatus.ACTIVE,
        )
        workspace.record_event(WorkspaceCreated(aggregate_id=workspace.id, org_id=org_id, name=name))
        return workspace

    def assert_active(self) -> None:
        if self.status != WorkspaceStatus.ACTIVE:
            raise WorkspaceNotActiveError(self.status.value)

    def rename(self, name: str) -> None:
        self.name = name
        self.record_event(WorkspaceUpdated(aggregate_id=self.id))

    def update_description(self, description: str) -> None:
        self.description = description
        self.record_event(WorkspaceUpdated(aggregate_id=self.id))

    def update_settings(self, patch: dict[str, Any]) -> None:
        self.settings = {**self.settings, **patch}
        self.record_event(WorkspaceUpdated(aggregate_id=self.id))

    def archive(self) -> None:
        self.status = WorkspaceStatus.ARCHIVED
        self.record_event(WorkspaceArchived(aggregate_id=self.id))

    def reactivate(self) -> None:
        self.status = WorkspaceStatus.ACTIVE
        self.record_event(WorkspaceReactivated(aggregate_id=self.id))


class WorkspaceMembership:
    """Hard-deletable join entity, same convention as Identity's
    TeamMembership/UserRoleAssignment."""

    def __init__(
        self, *, id: EntityId, workspace_id: EntityId, user_id: UserId, role: WorkspaceRole, joined_at: datetime | None = None
    ) -> None:
        self.id = id
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.role = role
        self.joined_at = joined_at or utcnow()

    @classmethod
    def create(cls, *, workspace_id: EntityId, user_id: UserId, role: WorkspaceRole = WorkspaceRole.MEMBER) -> "WorkspaceMembership":
        return cls(id=EntityId(new_uuid7()), workspace_id=workspace_id, user_id=user_id, role=role)


class Project(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        workspace_id: EntityId,
        org_id: OrgId,
        name: str,
        description: str,
        status: ProjectStatus,
        visibility: ProjectVisibility,
        metadata: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        template_id: EntityId | None = None,
        archived_at: datetime | None = None,
        deleted_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.workspace_id = workspace_id
        self.org_id = org_id
        self.name = name
        self.description = description
        self.status = status
        self.visibility = visibility
        self.metadata = metadata or {}
        self.settings = settings or {}
        self.template_id = template_id
        self.archived_at = archived_at
        self.deleted_at = deleted_at
        self.version = version

    @classmethod
    def create(
        cls,
        *,
        workspace_id: EntityId,
        org_id: OrgId,
        name: str,
        description: str = "",
        visibility: ProjectVisibility = ProjectVisibility.WORKSPACE,
        metadata: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        template_id: EntityId | None = None,
    ) -> "Project":
        project = cls(
            id=EntityId(new_uuid7()), workspace_id=workspace_id, org_id=org_id, name=name, description=description,
            status=ProjectStatus.PLANNING, visibility=visibility, metadata=metadata, settings=settings,
            template_id=template_id,
        )
        project.record_event(
            ProjectCreated(aggregate_id=project.id, workspace_id=workspace_id, org_id=org_id, name=name, template_id=template_id)
        )
        return project

    def assert_not_deleted(self) -> None:
        if self.deleted_at is not None:
            raise ProjectAlreadyDeletedError()

    def update(self, *, name: str | None = None, description: str | None = None) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        self.record_event(ProjectUpdated(aggregate_id=self.id))

    def update_metadata(self, patch: dict[str, Any]) -> None:
        self.metadata = {**self.metadata, **patch}
        self.record_event(ProjectUpdated(aggregate_id=self.id))

    def update_settings(self, patch: dict[str, Any]) -> None:
        self.settings = {**self.settings, **patch}
        self.record_event(ProjectUpdated(aggregate_id=self.id))

    def change_status(self, target_status: ProjectStatus) -> None:
        if target_status == self.status:
            return
        allowed = _ALLOWED_PROJECT_STATUS_TRANSITIONS.get(self.status, frozenset())
        if target_status not in allowed:
            raise InvalidProjectStatusTransitionError(self.status.value, target_status.value)
        self.status = target_status
        self.archived_at = utcnow() if target_status == ProjectStatus.ARCHIVED else None
        self.record_event(ProjectStatusChanged(aggregate_id=self.id, status=target_status.value))

    def change_visibility(self, visibility: ProjectVisibility) -> None:
        self.visibility = visibility
        self.record_event(ProjectVisibilityChanged(aggregate_id=self.id, visibility=visibility.value))

    def archive(self) -> None:
        self.change_status(ProjectStatus.ARCHIVED)
        self.record_event(ProjectArchived(aggregate_id=self.id))

    def unarchive(self) -> None:
        self.change_status(ProjectStatus.ACTIVE)
        self.record_event(ProjectUnarchived(aggregate_id=self.id))

    def mark_deleted(self) -> None:
        self.assert_not_deleted()
        self.deleted_at = utcnow()
        self.record_event(ProjectDeleted(aggregate_id=self.id))


class ProjectMembership:
    def __init__(
        self,
        *,
        id: EntityId,
        project_id: EntityId,
        user_id: UserId,
        role: ProjectRole,
        status: MembershipStatus,
        invited_by: UserId | None = None,
        invited_at: datetime | None = None,
        joined_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.user_id = user_id
        self.role = role
        self.status = status
        self.invited_by = invited_by
        self.invited_at = invited_at or utcnow()
        self.joined_at = joined_at

    @classmethod
    def invite(
        cls, *, project_id: EntityId, user_id: UserId, role: ProjectRole, invited_by: UserId
    ) -> "ProjectMembership":
        return cls(
            id=EntityId(new_uuid7()), project_id=project_id, user_id=user_id, role=role,
            status=MembershipStatus.INVITED, invited_by=invited_by,
        )

    @classmethod
    def add_directly(cls, *, project_id: EntityId, user_id: UserId, role: ProjectRole) -> "ProjectMembership":
        """Used for the project creator, who is an active owner from the
        first moment — no invite/accept round trip for oneself."""
        return cls(
            id=EntityId(new_uuid7()), project_id=project_id, user_id=user_id, role=role,
            status=MembershipStatus.ACTIVE, joined_at=utcnow(),
        )

    def accept(self) -> None:
        self.status = MembershipStatus.ACTIVE
        self.joined_at = utcnow()

    def change_role(self, role: ProjectRole) -> None:
        self.role = role

    def is_owner(self) -> bool:
        return self.role == ProjectRole.OWNER and self.status == MembershipStatus.ACTIVE


class ProjectTemplate(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        name: str,
        description: str,
        is_default: bool,
        default_status: ProjectStatus,
        default_visibility: ProjectVisibility,
        default_metadata: dict[str, Any] | None = None,
        default_settings: dict[str, Any] | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.name = name
        self.description = description
        self.is_default = is_default
        self.default_status = default_status
        self.default_visibility = default_visibility
        self.default_metadata = default_metadata or {}
        self.default_settings = default_settings or {}
        self.version = version

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        name: str,
        description: str = "",
        default_visibility: ProjectVisibility = ProjectVisibility.WORKSPACE,
        default_metadata: dict[str, Any] | None = None,
        default_settings: dict[str, Any] | None = None,
        is_default: bool = False,
    ) -> "ProjectTemplate":
        template = cls(
            id=EntityId(new_uuid7()), org_id=org_id, name=name, description=description, is_default=is_default,
            default_status=ProjectStatus.PLANNING, default_visibility=default_visibility,
            default_metadata=default_metadata, default_settings=default_settings,
        )
        template.record_event(ProjectTemplateCreated(aggregate_id=template.id, org_id=org_id, name=name))
        return template

    def update(self, *, name: str | None = None, description: str | None = None) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        self.record_event(ProjectTemplateUpdated(aggregate_id=self.id))

    def mark_default(self) -> None:
        self.is_default = True
        self.record_event(ProjectTemplateUpdated(aggregate_id=self.id))

    def unmark_default(self) -> None:
        self.is_default = False
        self.record_event(ProjectTemplateUpdated(aggregate_id=self.id))

    def mark_deleted(self) -> None:
        self.record_event(ProjectTemplateDeleted(aggregate_id=self.id))

    def to_export_dict(self) -> dict[str, Any]:
        """Template Export: a self-contained, re-importable representation.
        Deliberately excludes id/org_id/version — those are assigned fresh
        on import, since a template exported from one org may be imported
        into another."""
        return {
            "schema_version": 1,
            "name": self.name,
            "description": self.description,
            "default_visibility": self.default_visibility.value,
            "default_metadata": self.default_metadata,
            "default_settings": self.default_settings,
        }

    @classmethod
    def from_import_dict(cls, *, org_id: OrgId, data: dict[str, Any]) -> "ProjectTemplate":
        """Deliberately does not go through .create() — that would also
        record ProjectTemplateCreated, and an import should be observably
        distinct from an org authoring a template from scratch."""
        template = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            name=data["name"],
            description=data.get("description", ""),
            is_default=False,
            default_status=ProjectStatus.PLANNING,
            default_visibility=ProjectVisibility(data.get("default_visibility", ProjectVisibility.WORKSPACE.value)),
            default_metadata=data.get("default_metadata", {}),
            default_settings=data.get("default_settings", {}),
        )
        template.record_event(ProjectTemplateImported(aggregate_id=template.id, org_id=org_id, name=template.name))
        return template
