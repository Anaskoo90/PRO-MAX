"""Projects & Workspaces domain events — in-process only, mirroring
app.identity.domain.events' shape and conventions exactly."""

from __future__ import annotations

from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class WorkspaceCreated(DomainEvent):
    event_type = "projects.workspace_created"
    org_id: UUID
    name: str


class WorkspaceArchived(DomainEvent):
    event_type = "projects.workspace_archived"


class WorkspaceReactivated(DomainEvent):
    event_type = "projects.workspace_reactivated"


class WorkspaceUpdated(DomainEvent):
    event_type = "projects.workspace_updated"


class WorkspaceMemberAdded(DomainEvent):
    event_type = "projects.workspace_member_added"
    user_id: UUID
    role: str


class WorkspaceMemberRemoved(DomainEvent):
    event_type = "projects.workspace_member_removed"
    user_id: UUID


class ProjectCreated(DomainEvent):
    event_type = "projects.project_created"
    workspace_id: UUID
    org_id: UUID
    name: str
    template_id: UUID | None = None


class ProjectUpdated(DomainEvent):
    event_type = "projects.project_updated"


class ProjectStatusChanged(DomainEvent):
    event_type = "projects.project_status_changed"
    status: str


class ProjectVisibilityChanged(DomainEvent):
    event_type = "projects.project_visibility_changed"
    visibility: str


class ProjectArchived(DomainEvent):
    event_type = "projects.project_archived"


class ProjectUnarchived(DomainEvent):
    event_type = "projects.project_unarchived"


class ProjectDeleted(DomainEvent):
    event_type = "projects.project_deleted"


class ProjectMemberInvited(DomainEvent):
    event_type = "projects.project_member_invited"
    user_id: UUID
    role: str


class ProjectMemberJoined(DomainEvent):
    event_type = "projects.project_member_joined"
    user_id: UUID


class ProjectMemberRemoved(DomainEvent):
    event_type = "projects.project_member_removed"
    user_id: UUID


class ProjectMemberRoleChanged(DomainEvent):
    event_type = "projects.project_member_role_changed"
    user_id: UUID
    role: str


class ProjectTemplateCreated(DomainEvent):
    event_type = "projects.template_created"
    org_id: UUID
    name: str


class ProjectTemplateImported(DomainEvent):
    event_type = "projects.template_imported"
    org_id: UUID
    name: str


class ProjectTemplateDeleted(DomainEvent):
    event_type = "projects.template_deleted"


class ProjectTemplateUpdated(DomainEvent):
    event_type = "projects.template_updated"
