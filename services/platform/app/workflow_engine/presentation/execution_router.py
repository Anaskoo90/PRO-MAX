"""Runtime HTTP routes: enroll a task, execute a transition, inspect the
Audit Trail (submodule 8), and the Required Approval / Required Checklist
Completion prerequisite endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.workflow_engine.application.execution_service import WorkflowExecutionService
from app.workflow_engine.presentation import deps
from app.workflow_engine.presentation.schemas import (
    CompleteChecklistItemRequest,
    DecideApprovalRequest,
    EnrollTaskRequest,
    ExecuteTransitionRequest,
    RequestApprovalRequest,
    WorkflowApprovalRequestResponse,
    WorkflowExecutionRecordResponse,
    WorkflowTaskStateResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["workflow-execution"])


def _task_state_response(dto) -> WorkflowTaskStateResponse:
    return WorkflowTaskStateResponse(id=dto.id, workflow_id=dto.workflow_id, task_id=dto.task_id, current_state_id=dto.current_state_id, updated_at=dto.updated_at)


def _approval_response(dto) -> WorkflowApprovalRequestResponse:
    return WorkflowApprovalRequestResponse(
        id=dto.id, transition_id=dto.transition_id, task_id=dto.task_id, status=dto.status, requested_by=dto.requested_by,
        requested_at=dto.requested_at, decided_by=dto.decided_by, decided_at=dto.decided_at, reason=dto.reason,
    )


@router.post("/workflows/{workflow_id}/enroll", response_model=DataResponse[WorkflowTaskStateResponse], status_code=201)
async def enroll_task(
    workflow_id: str,
    request: EnrollTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> DataResponse[WorkflowTaskStateResponse]:
    task_state = await service.enroll_task(workflow_id=UUID(workflow_id), task_id=request.task_id, actor_user_id=claims.subject_user_id)
    return DataResponse(data=_task_state_response(task_state))


@router.get("/workflows/{workflow_id}/tasks/{task_id}/state", response_model=DataResponse[WorkflowTaskStateResponse])
async def get_task_state(
    workflow_id: str,
    task_id: str,
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> DataResponse[WorkflowTaskStateResponse]:
    task_state = await service.get_task_state(workflow_id=UUID(workflow_id), task_id=UUID(task_id))
    return DataResponse(data=_task_state_response(task_state))


@router.post("/workflows/{workflow_id}/tasks/{task_id}/transition", response_model=DataResponse[WorkflowTaskStateResponse])
async def execute_transition(
    workflow_id: str,
    task_id: str,
    request: ExecuteTransitionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> DataResponse[WorkflowTaskStateResponse]:
    task_state = await service.execute_transition(
        workflow_id=UUID(workflow_id), task_id=UUID(task_id), transition_id=request.transition_id,
        actor_user_id=claims.subject_user_id, reason=request.reason,
    )
    return DataResponse(data=_task_state_response(task_state))


@router.get("/workflows/{workflow_id}/tasks/{task_id}/history", response_model=DataResponse[list[WorkflowExecutionRecordResponse]])
async def get_execution_history(
    workflow_id: str,
    task_id: str,
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> DataResponse[list[WorkflowExecutionRecordResponse]]:
    records = await service.list_execution_history(workflow_id=UUID(workflow_id), task_id=UUID(task_id))
    return DataResponse(data=[
        WorkflowExecutionRecordResponse(
            id=r.id, workflow_id=r.workflow_id, task_id=r.task_id, transition_id=r.transition_id,
            from_state_id=r.from_state_id, to_state_id=r.to_state_id, actor_user_id=r.actor_user_id, reason=r.reason,
            occurred_at=r.occurred_at,
        )
        for r in records
    ])


@router.post("/transitions/{transition_id}/approvals", response_model=DataResponse[WorkflowApprovalRequestResponse], status_code=201)
async def request_approval(
    transition_id: str,
    request: RequestApprovalRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> DataResponse[WorkflowApprovalRequestResponse]:
    approval = await service.request_approval(transition_id=UUID(transition_id), task_id=request.task_id, actor_user_id=claims.subject_user_id)
    return DataResponse(data=_approval_response(approval))


@router.post("/approvals/{approval_id}/decide", response_model=DataResponse[WorkflowApprovalRequestResponse])
async def decide_approval(
    approval_id: str,
    request: DecideApprovalRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> DataResponse[WorkflowApprovalRequestResponse]:
    approval = await service.decide_approval(approval_id=UUID(approval_id), actor_user_id=claims.subject_user_id, approved=request.approved, reason=request.reason)
    return DataResponse(data=_approval_response(approval))


@router.post("/checklist-items/{item_id}/complete", status_code=204)
async def complete_checklist_item(
    item_id: str,
    request: CompleteChecklistItemRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowExecutionService = Depends(deps.get_workflow_execution_service),
) -> None:
    await service.complete_checklist_item(item_id=UUID(item_id), task_id=request.task_id, actor_user_id=claims.subject_user_id)
