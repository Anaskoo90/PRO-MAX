"""Project Templates HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.projects.application.template_management import ProjectTemplateService
from app.projects.domain.entities import ProjectVisibility
from app.projects.presentation import deps
from app.identity.presentation.authorization import assert_path_org_matches_claims
from app.projects.presentation.schemas import (
    CreateProjectTemplateRequest,
    ImportProjectTemplateRequest,
    ProjectTemplateExportResponse,
    ProjectTemplateResponse,
    UpdateProjectTemplateRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["project-templates"])


def _to_response(dto) -> ProjectTemplateResponse:
    return ProjectTemplateResponse(
        id=dto.id, org_id=dto.org_id, name=dto.name, description=dto.description, is_default=dto.is_default,
        default_visibility=dto.default_visibility, default_metadata=dto.default_metadata,
        default_settings=dto.default_settings,
    )


@router.post("/project-templates", response_model=DataResponse[ProjectTemplateResponse], status_code=201)
async def create_project_template(
    request: CreateProjectTemplateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> DataResponse[ProjectTemplateResponse]:
    template = await service.create_template(
        org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name, description=request.description,
        default_visibility=ProjectVisibility(request.default_visibility), default_metadata=request.default_metadata,
        default_settings=request.default_settings,
    )
    return DataResponse(data=_to_response(template))


@router.post("/project-templates/import", response_model=DataResponse[ProjectTemplateResponse], status_code=201)
async def import_project_template(
    request: ImportProjectTemplateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> DataResponse[ProjectTemplateResponse]:
    template = await service.import_template(org_id=claims.org_id, actor_user_id=claims.subject_user_id, data=request.data)
    return DataResponse(data=_to_response(template))


@router.get("/project-templates/{template_id}/export", response_model=DataResponse[ProjectTemplateExportResponse])
async def export_project_template(
    template_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> DataResponse[ProjectTemplateExportResponse]:
    data = await service.export_template_for_org(org_id=claims.org_id, template_id=UUID(template_id))
    return DataResponse(data=ProjectTemplateExportResponse(data=data))


@router.get("/organizations/{org_id}/project-templates", response_model=DataResponse[list[ProjectTemplateResponse]])
async def list_project_templates(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> DataResponse[list[ProjectTemplateResponse]]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    templates = await service.list_for_org(org_id=parsed_org_id)
    return DataResponse(data=[_to_response(t) for t in templates])


@router.patch("/project-templates/{template_id}", response_model=DataResponse[ProjectTemplateResponse])
async def update_project_template(
    template_id: str,
    request: UpdateProjectTemplateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> DataResponse[ProjectTemplateResponse]:
    template = await service.update_template(
        template_id=UUID(template_id), actor_user_id=claims.subject_user_id, name=request.name, description=request.description
    )
    return DataResponse(data=_to_response(template))


@router.post("/project-templates/{template_id}/set-default", response_model=DataResponse[ProjectTemplateResponse])
async def set_default_project_template(
    template_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> DataResponse[ProjectTemplateResponse]:
    template = await service.set_default(template_id=UUID(template_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(template))


@router.delete("/project-templates/{template_id}", status_code=204)
async def delete_project_template(
    template_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectTemplateService = Depends(deps.get_project_template_service),
) -> None:
    await service.delete_template(template_id=UUID(template_id), actor_user_id=claims.subject_user_id)
