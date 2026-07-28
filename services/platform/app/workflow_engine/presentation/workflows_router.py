"""Workflow Aggregate HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.workflow_engine.application.workflow_management import WorkflowService
from app.workflow_engine.presentation import deps
from app.workflow_engine.presentation.schemas import CreateWorkflowRequest, UpdateWorkflowRequest, WorkflowResponse
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["workflows"])


def _to_response(dto) -> WorkflowResponse:
    return WorkflowResponse(
        id=dto.id, project_id=dto.project_id, org_id=dto.org_id, name=dto.name, description=dto.description,
        status=dto.status, archived_at=dto.archived_at,
    )


@router.post("/projects/{project_id}/workflows", response_model=DataResponse[WorkflowResponse], status_code=201)
async def create_workflow(
    project_id: str,
    request: CreateWorkflowRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowResponse]:
    workflow = await service.create_workflow(
        project_id=UUID(project_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name,
        description=request.description,
    )
    return DataResponse(data=_to_response(workflow))


@router.get("/projects/{project_id}/workflows", response_model=DataResponse[list[WorkflowResponse]])
async def list_workflows(
    project_id: str,
    include_archived: bool = False,
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[list[WorkflowResponse]]:
    workflows = await service.list_for_project(project_id=UUID(project_id), include_archived=include_archived)
    return DataResponse(data=[_to_response(w) for w in workflows])


@router.get("/workflows/{workflow_id}", response_model=DataResponse[WorkflowResponse])
async def get_workflow(
    workflow_id: str,
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowResponse]:
    workflow = await service.get(workflow_id=UUID(workflow_id))
    return DataResponse(data=_to_response(workflow))


@router.patch("/workflows/{workflow_id}", response_model=DataResponse[WorkflowResponse])
async def update_workflow(
    workflow_id: str,
    request: UpdateWorkflowRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowResponse]:
    workflow = await service.update(workflow_id=UUID(workflow_id), actor_user_id=claims.subject_user_id, name=request.name, description=request.description)
    return DataResponse(data=_to_response(workflow))


@router.post("/workflows/{workflow_id}/archive", response_model=DataResponse[WorkflowResponse])
async def archive_workflow(
    workflow_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowResponse]:
    workflow = await service.archive(workflow_id=UUID(workflow_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(workflow))


@router.post("/workflows/{workflow_id}/restore", response_model=DataResponse[WorkflowResponse])
async def restore_workflow(
    workflow_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowResponse]:
    workflow = await service.restore(workflow_id=UUID(workflow_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(workflow))


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> None:
    await service.delete(workflow_id=UUID(workflow_id), actor_user_id=claims.subject_user_id)
