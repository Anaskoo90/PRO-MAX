"""Project Aggregate HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.projects.application.project_management import ProjectService
from app.projects.domain.entities import ProjectStatus, ProjectVisibility
from app.projects.presentation import deps
from app.projects.presentation.schemas import (
    ChangeProjectStatusRequest,
    ChangeProjectVisibilityRequest,
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectMetadataRequest,
    UpdateProjectRequest,
    UpdateProjectSettingsRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["projects"])


def _to_response(dto) -> ProjectResponse:
    return ProjectResponse(
        id=dto.id, workspace_id=dto.workspace_id, org_id=dto.org_id, name=dto.name, description=dto.description,
        status=dto.status, visibility=dto.visibility, metadata=dto.metadata, settings=dto.settings,
        template_id=dto.template_id, archived_at=dto.archived_at,
    )


@router.post("/workspaces/{workspace_id}/projects", response_model=DataResponse[ProjectResponse], status_code=201)
async def create_project(
    workspace_id: str,
    request: CreateProjectRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.create_project(
        workspace_id=UUID(workspace_id), actor_user_id=claims.subject_user_id, name=request.name,
        description=request.description,
        visibility=ProjectVisibility(request.visibility) if request.visibility else None,
        metadata=request.metadata, settings=request.settings,
        template_id=request.template_id,
    )
    return DataResponse(data=_to_response(project))


@router.get("/workspaces/{workspace_id}/projects", response_model=DataResponse[list[ProjectResponse]])
async def list_projects(
    workspace_id: str,
    include_archived: bool = False,
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[list[ProjectResponse]]:
    projects = await service.list_for_workspace(workspace_id=UUID(workspace_id), include_archived=include_archived)
    return DataResponse(data=[_to_response(p) for p in projects])


@router.get("/projects/{project_id}", response_model=DataResponse[ProjectResponse])
async def get_project(
    project_id: str,
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.get(project_id=UUID(project_id))
    return DataResponse(data=_to_response(project))


@router.patch("/projects/{project_id}", response_model=DataResponse[ProjectResponse])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.update(
        project_id=UUID(project_id), actor_user_id=claims.subject_user_id, name=request.name, description=request.description
    )
    return DataResponse(data=_to_response(project))


@router.put("/projects/{project_id}/metadata", response_model=DataResponse[ProjectResponse])
async def update_project_metadata(
    project_id: str,
    request: UpdateProjectMetadataRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.update_metadata(project_id=UUID(project_id), actor_user_id=claims.subject_user_id, patch=request.metadata)
    return DataResponse(data=_to_response(project))


@router.put("/projects/{project_id}/settings", response_model=DataResponse[ProjectResponse])
async def update_project_settings(
    project_id: str,
    request: UpdateProjectSettingsRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.update_settings(project_id=UUID(project_id), actor_user_id=claims.subject_user_id, patch=request.settings)
    return DataResponse(data=_to_response(project))


@router.post("/projects/{project_id}/status", response_model=DataResponse[ProjectResponse])
async def change_project_status(
    project_id: str,
    request: ChangeProjectStatusRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.change_status(
        project_id=UUID(project_id), actor_user_id=claims.subject_user_id, status=ProjectStatus(request.status)
    )
    return DataResponse(data=_to_response(project))


@router.post("/projects/{project_id}/visibility", response_model=DataResponse[ProjectResponse])
async def change_project_visibility(
    project_id: str,
    request: ChangeProjectVisibilityRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.change_visibility(
        project_id=UUID(project_id), actor_user_id=claims.subject_user_id, visibility=ProjectVisibility(request.visibility)
    )
    return DataResponse(data=_to_response(project))


@router.post("/projects/{project_id}/archive", response_model=DataResponse[ProjectResponse])
async def archive_project(
    project_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.archive(project_id=UUID(project_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(project))


@router.post("/projects/{project_id}/unarchive", response_model=DataResponse[ProjectResponse])
async def unarchive_project(
    project_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> DataResponse[ProjectResponse]:
    project = await service.unarchive(project_id=UUID(project_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(project))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectService = Depends(deps.get_project_service),
) -> None:
    await service.delete(project_id=UUID(project_id), actor_user_id=claims.subject_user_id)
