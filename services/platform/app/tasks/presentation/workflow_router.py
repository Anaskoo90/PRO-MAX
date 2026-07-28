"""Configurable Workflow HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.tasks.application.workflow_management import WorkflowService
from app.tasks.presentation import deps
from app.tasks.presentation.schemas import CreateWorkflowDefinitionRequest, WorkflowDefinitionResponse
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["workflows"])


def _to_response(dto) -> WorkflowDefinitionResponse:
    return WorkflowDefinitionResponse(
        id=dto.id, project_id=dto.project_id, name=dto.name, statuses=dto.statuses, transitions=dto.transitions
    )


@router.put("/projects/{project_id}/workflow", response_model=DataResponse[WorkflowDefinitionResponse])
async def create_or_replace_workflow(
    project_id: str,
    request: CreateWorkflowDefinitionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowDefinitionResponse]:
    workflow = await service.create_or_replace_workflow(
        project_id=UUID(project_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name,
        statuses=request.statuses, transitions=request.transitions,
    )
    return DataResponse(data=_to_response(workflow))


@router.get("/projects/{project_id}/workflow", response_model=DataResponse[WorkflowDefinitionResponse])
async def get_workflow(
    project_id: str,
    service: WorkflowService = Depends(deps.get_workflow_service),
) -> DataResponse[WorkflowDefinitionResponse]:
    workflow = await service.get_for_project(project_id=UUID(project_id))
    return DataResponse(data=_to_response(workflow))
