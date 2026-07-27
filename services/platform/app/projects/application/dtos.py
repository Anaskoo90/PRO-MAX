"""Application-layer DTOs for the Projects & Workspaces context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WorkspaceDTO:
    id: UUID
    org_id: UUID
    name: str
    slug: str
    description: str
    status: str
    settings: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkspaceMembershipDTO:
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectDTO:
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


@dataclass(frozen=True, slots=True)
class ProjectMembershipDTO:
    id: UUID
    project_id: UUID
    user_id: UUID
    role: str
    status: str
    invited_by: UUID | None
    invited_at: datetime
    joined_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProjectTemplateDTO:
    id: UUID
    org_id: UUID
    name: str
    description: str
    is_default: bool
    default_visibility: str
    default_metadata: dict[str, Any]
    default_settings: dict[str, Any]
