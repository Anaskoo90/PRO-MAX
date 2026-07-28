"""Task Assignment HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.tasks.application.task_assignment import TaskAssignmentService
from app.tasks.presentation import deps
from app.tasks.presentation.schemas import (
    AssignTaskRequest,
    ReassignTaskRequest,
    TaskAssignmentHistoryResponse,
    TaskAssignmentResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["task-assignments"])


def _to_response(dto) -> TaskAssignmentResponse:
    return TaskAssignmentResponse(
        id=dto.id, task_id=dto.task_id, user_id=dto.user_id, assigned_by=dto.assigned_by, is_primary=dto.is_primary,
        assigned_at=dto.assigned_at,
    )


def _history_response(dto) -> TaskAssignmentHistoryResponse:
    return TaskAssignmentHistoryResponse(
        id=dto.id, task_id=dto.task_id, user_id=dto.user_id, action=dto.action, actor_user_id=dto.actor_user_id,
        occurred_at=dto.occurred_at,
    )


@router.post("/tasks/{task_id}/assignments", response_model=DataResponse[TaskAssignmentResponse], status_code=201)
async def assign_task(
    task_id: str,
    request: AssignTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskAssignmentService = Depends(deps.get_task_assignment_service),
) -> DataResponse[TaskAssignmentResponse]:
    assignment = await service.assign(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, assignee_user_id=request.assignee_user_id,
        is_primary=request.is_primary,
    )
    return DataResponse(data=_to_response(assignment))


@router.get("/tasks/{task_id}/assignments", response_model=DataResponse[list[TaskAssignmentResponse]])
async def list_task_assignments(
    task_id: str,
    service: TaskAssignmentService = Depends(deps.get_task_assignment_service),
) -> DataResponse[list[TaskAssignmentResponse]]:
    assignments = await service.list_assignments(task_id=UUID(task_id))
    return DataResponse(data=[_to_response(a) for a in assignments])


@router.delete("/tasks/{task_id}/assignments/{user_id}", status_code=204)
async def unassign_task(
    task_id: str,
    user_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskAssignmentService = Depends(deps.get_task_assignment_service),
) -> None:
    await service.unassign(task_id=UUID(task_id), actor_user_id=claims.subject_user_id, assignee_user_id=UUID(user_id))


@router.post("/tasks/{task_id}/assignments/reassign", response_model=DataResponse[TaskAssignmentResponse])
async def reassign_task(
    task_id: str,
    request: ReassignTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskAssignmentService = Depends(deps.get_task_assignment_service),
) -> DataResponse[TaskAssignmentResponse]:
    assignment = await service.reassign(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, from_user_id=request.from_user_id,
        to_user_id=request.to_user_id,
    )
    return DataResponse(data=_to_response(assignment))


@router.get("/tasks/{task_id}/assignments/history", response_model=DataResponse[list[TaskAssignmentHistoryResponse]])
async def list_task_assignment_history(
    task_id: str,
    service: TaskAssignmentService = Depends(deps.get_task_assignment_service),
) -> DataResponse[list[TaskAssignmentHistoryResponse]]:
    history = await service.list_history(task_id=UUID(task_id))
    return DataResponse(data=[_history_response(h) for h in history])
