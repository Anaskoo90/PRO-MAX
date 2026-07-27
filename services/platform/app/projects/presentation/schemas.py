"""Request/response schemas for the Projects & Workspaces API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=50)
    description: str = ""


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class UpdateWorkspaceSettingsRequest(BaseModel):
    settings: dict[str, Any]


class WorkspaceResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    slug: str
    description: str
    status: str
    settings: dict[str, Any]


class AddWorkspaceMemberRequest(BaseModel):
    user_id: UUID
    role: str = "member"


class WorkspaceMembershipResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    joined_at: datetime


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    visibility: str | None = None
    metadata: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    template_id: UUID | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class UpdateProjectMetadataRequest(BaseModel):
    metadata: dict[str, Any]


class UpdateProjectSettingsRequest(BaseModel):
    settings: dict[str, Any]


class ChangeProjectStatusRequest(BaseModel):
    status: str


class ChangeProjectVisibilityRequest(BaseModel):
    visibility: str


class ProjectResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    org_id: UUID
    name: str
    description: str
    status: str
    visibility: str
    metadata: dict[str, Any]
    settings: dict[str, Any]
    template_id: UUID | None
    archived_at: datetime | None


class InviteProjectMemberRequest(BaseModel):
    email: EmailStr
    role: str = "contributor"


class ChangeProjectMemberRoleRequest(BaseModel):
    role: str


class ProjectMembershipResponse(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    role: str
    status: str
    invited_by: UUID | None
    invited_at: datetime
    joined_at: datetime | None


class CreateProjectTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    default_visibility: str = "workspace"
    default_metadata: dict[str, Any] = {}
    default_settings: dict[str, Any] = {}


class UpdateProjectTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ImportProjectTemplateRequest(BaseModel):
    data: dict[str, Any]


class ProjectTemplateResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: str
    is_default: bool
    default_visibility: str
    default_metadata: dict[str, Any]
    default_settings: dict[str, Any]


class ProjectTemplateExportResponse(BaseModel):
    data: dict[str, Any]
