"""Task Aggregate + Lifecycle + Dates + Query HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.tasks.application.dtos import TaskListFilter
from app.tasks.application.task_lifecycle import TaskLifecycleService
from app.tasks.application.task_management import TaskService
from app.tasks.application.task_query_service import TaskQueryService
from app.tasks.application.task_scheduling import TaskSchedulingService
from app.tasks.domain.workflow import TaskPriority, TaskStatus
from app.tasks.presentation import deps
from app.tasks.presentation.schemas import (
    ChangeTaskPriorityRequest,
    ChangeTaskStatusRequest,
    CreateTaskRequest,
    DuplicateTaskRequest,
    SetTaskDatesRequest,
    TaskResponse,
    TaskSearchRequest,
    UpdateTaskRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["tasks"])


def _to_response(dto) -> TaskResponse:
    return TaskResponse(
        id=dto.id, project_id=dto.project_id, org_id=dto.org_id, title=dto.title, description=dto.description,
        status=dto.status, priority=dto.priority, parent_task_id=dto.parent_task_id, position=dto.position,
        start_date=dto.start_date, due_date=dto.due_date, reminder_date=dto.reminder_date,
        completion_date=dto.completion_date, is_archived=dto.is_archived, archived_at=dto.archived_at,
        is_overdue=dto.is_overdue,
    )


@router.post("/projects/{project_id}/tasks", response_model=DataResponse[TaskResponse], status_code=201)
async def create_task(
    project_id: str,
    request: CreateTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskService = Depends(deps.get_task_service),
) -> DataResponse[TaskResponse]:
    task = await service.create_task(
        project_id=UUID(project_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id, title=request.title,
        description=request.description, priority=TaskPriority(request.priority), parent_task_id=request.parent_task_id,
        start_date=request.start_date, due_date=request.due_date, reminder_date=request.reminder_date,
    )
    return DataResponse(data=_to_response(task))


@router.get("/projects/{project_id}/tasks", response_model=DataResponse[list[TaskResponse]])
async def list_tasks(
    project_id: str,
    include_archived: bool = False,
    query_service: TaskQueryService = Depends(deps.get_task_query_service),
) -> DataResponse[list[TaskResponse]]:
    tasks = await query_service.list_for_project(project_id=UUID(project_id), include_archived=include_archived)
    return DataResponse(data=[_to_response(t) for t in tasks])


@router.post("/projects/{project_id}/tasks/search", response_model=DataResponse[list[TaskResponse]])
async def search_tasks(
    project_id: str,
    request: TaskSearchRequest,
    query_service: TaskQueryService = Depends(deps.get_task_query_service),
) -> DataResponse[list[TaskResponse]]:
    filters = TaskListFilter(
        status=request.status, priority=request.priority, label_id=request.label_id,
        assignee_user_id=request.assignee_user_id, search_text=request.search_text,
        include_archived=request.include_archived, parent_task_id=request.parent_task_id,
    )
    tasks = await query_service.search(project_id=UUID(project_id), filters=filters)
    return DataResponse(data=[_to_response(t) for t in tasks])


@router.get("/projects/{project_id}/tasks/overdue", response_model=DataResponse[list[TaskResponse]])
async def list_overdue_tasks(
    project_id: str,
    query_service: TaskQueryService = Depends(deps.get_task_query_service),
) -> DataResponse[list[TaskResponse]]:
    tasks = await query_service.list_overdue_for_project(project_id=UUID(project_id))
    return DataResponse(data=[_to_response(t) for t in tasks])


@router.get("/tasks/{task_id}", response_model=DataResponse[TaskResponse])
async def get_task(
    task_id: str,
    service: TaskService = Depends(deps.get_task_service),
) -> DataResponse[TaskResponse]:
    task = await service.get(task_id=UUID(task_id))
    return DataResponse(data=_to_response(task))


@router.patch("/tasks/{task_id}", response_model=DataResponse[TaskResponse])
async def update_task(
    task_id: str,
    request: UpdateTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskService = Depends(deps.get_task_service),
) -> DataResponse[TaskResponse]:
    task = await service.update(task_id=UUID(task_id), actor_user_id=claims.subject_user_id, title=request.title, description=request.description)
    return DataResponse(data=_to_response(task))


@router.post("/tasks/{task_id}/archive", response_model=DataResponse[TaskResponse])
async def archive_task(
    task_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskService = Depends(deps.get_task_service),
) -> DataResponse[TaskResponse]:
    task = await service.archive(task_id=UUID(task_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(task))


@router.post("/tasks/{task_id}/restore", response_model=DataResponse[TaskResponse])
async def restore_task(
    task_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskService = Depends(deps.get_task_service),
) -> DataResponse[TaskResponse]:
    task = await service.restore(task_id=UUID(task_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(task))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskService = Depends(deps.get_task_service),
) -> None:
    await service.delete(task_id=UUID(task_id), actor_user_id=claims.subject_user_id)


@router.post("/tasks/{task_id}/duplicate", response_model=DataResponse[TaskResponse], status_code=201)
async def duplicate_task(
    task_id: str,
    request: DuplicateTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskService = Depends(deps.get_task_service),
) -> DataResponse[TaskResponse]:
    task = await service.duplicate(task_id=UUID(task_id), actor_user_id=claims.subject_user_id, title=request.title)
    return DataResponse(data=_to_response(task))


@router.post("/tasks/{task_id}/status", response_model=DataResponse[TaskResponse])
async def change_task_status(
    task_id: str,
    request: ChangeTaskStatusRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskLifecycleService = Depends(deps.get_task_lifecycle_service),
) -> DataResponse[TaskResponse]:
    task = await service.change_status(task_id=UUID(task_id), actor_user_id=claims.subject_user_id, status=TaskStatus(request.status))
    return DataResponse(data=_to_response(task))


@router.post("/tasks/{task_id}/priority", response_model=DataResponse[TaskResponse])
async def change_task_priority(
    task_id: str,
    request: ChangeTaskPriorityRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskLifecycleService = Depends(deps.get_task_lifecycle_service),
) -> DataResponse[TaskResponse]:
    task = await service.change_priority(task_id=UUID(task_id), actor_user_id=claims.subject_user_id, priority=TaskPriority(request.priority))
    return DataResponse(data=_to_response(task))


@router.put("/tasks/{task_id}/dates", response_model=DataResponse[TaskResponse])
async def set_task_dates(
    task_id: str,
    request: SetTaskDatesRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskSchedulingService = Depends(deps.get_task_scheduling_service),
) -> DataResponse[TaskResponse]:
    task = await service.set_dates(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, start_date=request.start_date,
        due_date=request.due_date, reminder_date=request.reminder_date,
    )
    return DataResponse(data=_to_response(task))
