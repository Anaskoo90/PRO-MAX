"""Task Ordering HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.tasks.application.task_ordering import AutoOrderStrategy, TaskOrderingService
from app.tasks.presentation import deps
from app.tasks.presentation.schemas import MoveTaskRequest, TaskResponse
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["task-ordering"])


def _to_response(dto) -> TaskResponse:
    return TaskResponse(
        id=dto.id, project_id=dto.project_id, org_id=dto.org_id, title=dto.title, description=dto.description,
        status=dto.status, priority=dto.priority, parent_task_id=dto.parent_task_id, position=dto.position,
        start_date=dto.start_date, due_date=dto.due_date, reminder_date=dto.reminder_date,
        completion_date=dto.completion_date, is_archived=dto.is_archived, archived_at=dto.archived_at,
        is_overdue=dto.is_overdue,
    )


@router.put("/tasks/{task_id}/move", response_model=DataResponse[TaskResponse])
async def move_task(
    task_id: str,
    request: MoveTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskOrderingService = Depends(deps.get_task_ordering_service),
) -> DataResponse[TaskResponse]:
    task = await service.move_task(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, previous_task_id=request.previous_task_id,
        next_task_id=request.next_task_id,
    )
    return DataResponse(data=_to_response(task))


@router.get("/projects/{project_id}/tasks/auto-order", response_model=DataResponse[list[TaskResponse]])
async def list_auto_ordered_tasks(
    project_id: str,
    strategy: AutoOrderStrategy = AutoOrderStrategy.PRIORITY_DESC,
    service: TaskOrderingService = Depends(deps.get_task_ordering_service),
) -> DataResponse[list[TaskResponse]]:
    tasks = await service.list_auto_ordered(project_id=UUID(project_id), strategy=strategy)
    return DataResponse(data=[_to_response(t) for t in tasks])
