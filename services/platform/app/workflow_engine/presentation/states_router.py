"""Workflow States HTTP routes: custom states, initial/final/hidden/archived flags."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.workflow_engine.application.state_management import WorkflowStateService
from app.workflow_engine.presentation import deps
from app.workflow_engine.presentation.schemas import (
    CreateStateRequest,
    RenameStateRequest,
    ReorderStateRequest,
    SetMappedTaskStatusRequest,
    SetStateFlagRequest,
    WorkflowStateResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["workflow-states"])


def _to_response(dto) -> WorkflowStateResponse:
    return WorkflowStateResponse(
        id=dto.id, workflow_id=dto.workflow_id, name=dto.name, position=dto.position, is_initial=dto.is_initial,
        is_final=dto.is_final, is_hidden=dto.is_hidden, is_archived=dto.is_archived, mapped_task_status=dto.mapped_task_status,
    )


@router.post("/workflows/{workflow_id}/states", response_model=DataResponse[WorkflowStateResponse], status_code=201)
async def create_state(
    workflow_id: str,
    request: CreateStateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.create_state(
        workflow_id=UUID(workflow_id), actor_user_id=claims.subject_user_id, name=request.name,
        is_initial=request.is_initial, is_final=request.is_final, is_hidden=request.is_hidden,
        mapped_task_status=request.mapped_task_status,
    )
    return DataResponse(data=_to_response(state))


@router.get("/workflows/{workflow_id}/states", response_model=DataResponse[list[WorkflowStateResponse]])
async def list_states(
    workflow_id: str,
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[list[WorkflowStateResponse]]:
    states = await service.list_for_workflow(workflow_id=UUID(workflow_id))
    return DataResponse(data=[_to_response(s) for s in states])


@router.patch("/states/{state_id}", response_model=DataResponse[WorkflowStateResponse])
async def rename_state(
    state_id: str,
    request: RenameStateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.rename_state(state_id=UUID(state_id), actor_user_id=claims.subject_user_id, name=request.name)
    return DataResponse(data=_to_response(state))


@router.post("/states/{state_id}/set-initial", response_model=DataResponse[WorkflowStateResponse])
async def set_initial_state(
    state_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.set_initial(state_id=UUID(state_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(state))


@router.put("/states/{state_id}/final", response_model=DataResponse[WorkflowStateResponse])
async def set_final_state(
    state_id: str,
    request: SetStateFlagRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.set_final(state_id=UUID(state_id), actor_user_id=claims.subject_user_id, is_final=request.value)
    return DataResponse(data=_to_response(state))


@router.put("/states/{state_id}/hidden", response_model=DataResponse[WorkflowStateResponse])
async def set_hidden_state(
    state_id: str,
    request: SetStateFlagRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.set_hidden(state_id=UUID(state_id), actor_user_id=claims.subject_user_id, is_hidden=request.value)
    return DataResponse(data=_to_response(state))


@router.put("/states/{state_id}/archived", response_model=DataResponse[WorkflowStateResponse])
async def set_archived_state(
    state_id: str,
    request: SetStateFlagRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.set_archived(state_id=UUID(state_id), actor_user_id=claims.subject_user_id, is_archived=request.value)
    return DataResponse(data=_to_response(state))


@router.put("/states/{state_id}/mapped-status", response_model=DataResponse[WorkflowStateResponse])
async def set_mapped_task_status(
    state_id: str,
    request: SetMappedTaskStatusRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.set_mapped_task_status(state_id=UUID(state_id), actor_user_id=claims.subject_user_id, status=request.status)
    return DataResponse(data=_to_response(state))


@router.post("/states/{state_id}/reorder", response_model=DataResponse[WorkflowStateResponse])
async def reorder_state(
    state_id: str,
    request: ReorderStateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> DataResponse[WorkflowStateResponse]:
    state = await service.reorder_state(
        state_id=UUID(state_id), actor_user_id=claims.subject_user_id,
        previous_state_id=request.previous_state_id, next_state_id=request.next_state_id,
    )
    return DataResponse(data=_to_response(state))


@router.delete("/states/{state_id}", status_code=204)
async def delete_state(
    state_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowStateService = Depends(deps.get_workflow_state_service),
) -> None:
    await service.delete_state(state_id=UUID(state_id), actor_user_id=claims.subject_user_id)
