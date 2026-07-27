"""Workspace HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.projects.application.workspace_management import WorkspaceService
from app.projects.domain.entities import WorkspaceRole
from app.projects.presentation import deps
from app.projects.presentation.schemas import (
    AddWorkspaceMemberRequest,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    UpdateWorkspaceSettingsRequest,
    WorkspaceMembershipResponse,
    WorkspaceResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["workspaces"])


def _to_response(dto) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=dto.id, org_id=dto.org_id, name=dto.name, slug=dto.slug, description=dto.description, status=dto.status,
        settings=dto.settings,
    )


def _membership_response(dto) -> WorkspaceMembershipResponse:
    return WorkspaceMembershipResponse(id=dto.id, workspace_id=dto.workspace_id, user_id=dto.user_id, role=dto.role, joined_at=dto.joined_at)


@router.post("/workspaces", response_model=DataResponse[WorkspaceResponse], status_code=201)
async def create_workspace(
    request: CreateWorkspaceRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceResponse]:
    workspace = await service.create_workspace(
        org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name, slug=request.slug,
        description=request.description,
    )
    return DataResponse(data=_to_response(workspace))


@router.get("/organizations/{org_id}/workspaces", response_model=DataResponse[list[WorkspaceResponse]])
async def list_workspaces(
    org_id: str,
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[list[WorkspaceResponse]]:
    workspaces = await service.list_for_org(org_id=UUID(org_id))
    return DataResponse(data=[_to_response(w) for w in workspaces])


@router.get("/workspaces/{workspace_id}", response_model=DataResponse[WorkspaceResponse])
async def get_workspace(
    workspace_id: str,
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceResponse]:
    workspace = await service.get(workspace_id=UUID(workspace_id))
    return DataResponse(data=_to_response(workspace))


@router.patch("/workspaces/{workspace_id}", response_model=DataResponse[WorkspaceResponse])
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceResponse]:
    workspace = await service.update(
        workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id, name=request.name,
        description=request.description,
    )
    return DataResponse(data=_to_response(workspace))


@router.put("/workspaces/{workspace_id}/settings", response_model=DataResponse[WorkspaceResponse])
async def update_workspace_settings(
    workspace_id: str,
    request: UpdateWorkspaceSettingsRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceResponse]:
    workspace = await service.update_settings(workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id, patch=request.settings)
    return DataResponse(data=_to_response(workspace))


@router.post("/workspaces/{workspace_id}/archive", response_model=DataResponse[WorkspaceResponse])
async def archive_workspace(
    workspace_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceResponse]:
    workspace = await service.archive(workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(workspace))


@router.post("/workspaces/{workspace_id}/reactivate", response_model=DataResponse[WorkspaceResponse])
async def reactivate_workspace(
    workspace_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceResponse]:
    workspace = await service.reactivate(workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(workspace))


@router.post("/workspaces/{workspace_id}/members", response_model=DataResponse[WorkspaceMembershipResponse], status_code=201)
async def add_workspace_member(
    workspace_id: str,
    request: AddWorkspaceMemberRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[WorkspaceMembershipResponse]:
    membership = await service.add_member(
        workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id, target_user_id=request.user_id,
        role=WorkspaceRole(request.role),
    )
    return DataResponse(data=_membership_response(membership))


@router.get("/workspaces/{workspace_id}/members", response_model=DataResponse[list[WorkspaceMembershipResponse]])
async def list_workspace_members(
    workspace_id: str,
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> DataResponse[list[WorkspaceMembershipResponse]]:
    memberships = await service.list_members(workspace_id=UUID(workspace_id))
    return DataResponse(data=[_membership_response(m) for m in memberships])


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
async def remove_workspace_member(
    workspace_id: str,
    user_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkspaceService = Depends(deps.get_workspace_service),
) -> None:
    await service.remove_member(workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id, target_user_id=UUID(user_id))
