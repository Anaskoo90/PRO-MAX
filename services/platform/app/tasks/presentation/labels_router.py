"""Labels HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.tasks.application.label_management import LabelService
from app.tasks.presentation import deps
from app.tasks.presentation.schemas import CreateLabelRequest, LabelResponse, UpdateLabelRequest
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["labels"])


def _to_response(dto) -> LabelResponse:
    return LabelResponse(id=dto.id, project_id=dto.project_id, name=dto.name, color=dto.color)


@router.post("/projects/{project_id}/labels", response_model=DataResponse[LabelResponse], status_code=201)
async def create_label(
    project_id: str,
    request: CreateLabelRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: LabelService = Depends(deps.get_label_service),
) -> DataResponse[LabelResponse]:
    label = await service.create_label(
        project_id=UUID(project_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name,
        color=request.color,
    )
    return DataResponse(data=_to_response(label))


@router.get("/projects/{project_id}/labels", response_model=DataResponse[list[LabelResponse]])
async def list_labels(
    project_id: str,
    service: LabelService = Depends(deps.get_label_service),
) -> DataResponse[list[LabelResponse]]:
    labels = await service.list_for_project(project_id=UUID(project_id))
    return DataResponse(data=[_to_response(l) for l in labels])


@router.patch("/labels/{label_id}", response_model=DataResponse[LabelResponse])
async def update_label(
    label_id: str,
    request: UpdateLabelRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: LabelService = Depends(deps.get_label_service),
) -> DataResponse[LabelResponse]:
    label = await service.update_label(
        label_id=UUID(label_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name,
        color=request.color,
    )
    return DataResponse(data=_to_response(label))


@router.delete("/labels/{label_id}", status_code=204)
async def delete_label(
    label_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: LabelService = Depends(deps.get_label_service),
) -> None:
    await service.delete_label(label_id=UUID(label_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id)


@router.post("/tasks/{task_id}/labels/{label_id}", status_code=204)
async def attach_label(
    task_id: str,
    label_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: LabelService = Depends(deps.get_label_service),
) -> None:
    await service.attach_label(task_id=UUID(task_id), label_id=UUID(label_id), actor_user_id=claims.subject_user_id)


@router.delete("/tasks/{task_id}/labels/{label_id}", status_code=204)
async def detach_label(
    task_id: str,
    label_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: LabelService = Depends(deps.get_label_service),
) -> None:
    await service.detach_label(task_id=UUID(task_id), label_id=UUID(label_id), actor_user_id=claims.subject_user_id)


@router.get("/tasks/{task_id}/labels", response_model=DataResponse[list[LabelResponse]])
async def list_task_labels(
    task_id: str,
    service: LabelService = Depends(deps.get_label_service),
) -> DataResponse[list[LabelResponse]]:
    labels = await service.list_labels_for_task(task_id=UUID(task_id))
    return DataResponse(data=[_to_response(l) for l in labels])
