"""ORM row <-> domain entity mapping for the Projects & Workspaces context."""

from __future__ import annotations

from app.projects.domain.audit import ProjectsAuditEventCategory, ProjectsAuditLogRecord
from app.projects.domain.entities import (
    MembershipStatus,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    ProjectTemplate,
    ProjectVisibility,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceStatus,
)
from app.projects.infrastructure.orm_models import (
    ProjectMembershipOrmModel,
    ProjectOrmModel,
    ProjectsAuditLogOrmModel,
    ProjectTemplateOrmModel,
    WorkspaceMembershipOrmModel,
    WorkspaceOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def workspace_to_domain(row: WorkspaceOrmModel) -> Workspace:
    return Workspace(
        id=EntityId(row.id), org_id=OrgId(row.org_id), name=row.name, slug=row.slug, description=row.description,
        status=WorkspaceStatus(row.status), settings=row.settings, version=row.version,
    )


def workspace_to_orm(entity: Workspace, row: WorkspaceOrmModel | None = None) -> WorkspaceOrmModel:
    row = row or WorkspaceOrmModel(id=entity.id)
    row.org_id = entity.org_id
    row.name = entity.name
    row.slug = entity.slug
    row.description = entity.description
    row.status = entity.status.value
    row.settings = entity.settings
    row.version = entity.version
    return row


def workspace_membership_to_domain(row: WorkspaceMembershipOrmModel) -> WorkspaceMembership:
    return WorkspaceMembership(
        id=EntityId(row.id), workspace_id=EntityId(row.workspace_id), user_id=UserId(row.user_id),
        role=WorkspaceRole(row.role), joined_at=row.joined_at,
    )


def workspace_membership_to_orm(entity: WorkspaceMembership) -> WorkspaceMembershipOrmModel:
    return WorkspaceMembershipOrmModel(
        id=entity.id, workspace_id=entity.workspace_id, user_id=entity.user_id, role=entity.role.value,
    )


def project_to_domain(row: ProjectOrmModel) -> Project:
    return Project(
        id=EntityId(row.id), workspace_id=EntityId(row.workspace_id), org_id=OrgId(row.org_id), name=row.name,
        description=row.description, status=ProjectStatus(row.status), visibility=ProjectVisibility(row.visibility),
        metadata=row.metadata_, settings=row.settings,
        template_id=EntityId(row.template_id) if row.template_id else None,
        archived_at=row.archived_at, deleted_at=row.deleted_at, version=row.version,
    )


def project_to_orm(entity: Project, row: ProjectOrmModel | None = None) -> ProjectOrmModel:
    row = row or ProjectOrmModel(id=entity.id)
    row.workspace_id = entity.workspace_id
    row.org_id = entity.org_id
    row.name = entity.name
    row.description = entity.description
    row.status = entity.status.value
    row.visibility = entity.visibility.value
    row.metadata_ = entity.metadata
    row.settings = entity.settings
    row.template_id = entity.template_id
    row.archived_at = entity.archived_at
    row.deleted_at = entity.deleted_at
    row.version = entity.version
    return row


def project_membership_to_domain(row: ProjectMembershipOrmModel) -> ProjectMembership:
    return ProjectMembership(
        id=EntityId(row.id), project_id=EntityId(row.project_id), user_id=UserId(row.user_id),
        role=ProjectRole(row.role), status=MembershipStatus(row.status),
        invited_by=UserId(row.invited_by) if row.invited_by else None,
        invited_at=row.invited_at, joined_at=row.joined_at,
    )


def project_membership_to_orm(
    entity: ProjectMembership, row: ProjectMembershipOrmModel | None = None
) -> ProjectMembershipOrmModel:
    row = row or ProjectMembershipOrmModel(id=entity.id, project_id=entity.project_id, invited_at=entity.invited_at)
    row.user_id = entity.user_id
    row.role = entity.role.value
    row.status = entity.status.value
    row.invited_by = entity.invited_by
    row.joined_at = entity.joined_at
    return row


def project_template_to_domain(row: ProjectTemplateOrmModel) -> ProjectTemplate:
    return ProjectTemplate(
        id=EntityId(row.id), org_id=OrgId(row.org_id), name=row.name, description=row.description,
        is_default=row.is_default, default_status=ProjectStatus(row.default_status),
        default_visibility=ProjectVisibility(row.default_visibility), default_metadata=row.default_metadata,
        default_settings=row.default_settings, version=row.version,
    )


def project_template_to_orm(entity: ProjectTemplate, row: ProjectTemplateOrmModel | None = None) -> ProjectTemplateOrmModel:
    row = row or ProjectTemplateOrmModel(id=entity.id, org_id=entity.org_id)
    row.name = entity.name
    row.description = entity.description
    row.is_default = entity.is_default
    row.default_status = entity.default_status.value
    row.default_visibility = entity.default_visibility.value
    row.default_metadata = entity.default_metadata
    row.default_settings = entity.default_settings
    row.version = entity.version
    return row


def audit_log_to_domain(row: ProjectsAuditLogOrmModel) -> ProjectsAuditLogRecord:
    return ProjectsAuditLogRecord(
        id=EntityId(row.id), org_id=OrgId(row.org_id), category=ProjectsAuditEventCategory(row.category),
        action=row.action, actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type, resource_id=row.resource_id, metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: ProjectsAuditLogRecord) -> ProjectsAuditLogOrmModel:
    return ProjectsAuditLogOrmModel(
        id=entity.id, org_id=entity.org_id, category=entity.category.value, action=entity.action,
        actor_user_id=entity.actor_user_id, resource_type=entity.resource_type, resource_id=entity.resource_id,
        metadata_=entity.metadata, occurred_at=entity.occurred_at,
    )
