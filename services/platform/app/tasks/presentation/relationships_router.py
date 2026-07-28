"""Task Relationships HTTP routes: parent/subtask, dependencies, related tasks."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.tasks.application.task_relationships import TaskRelationshipService
from app.tasks.presentation import deps
from app.tasks.presentation.schemas import (
    AddDependencyRequest,
    AddRelatedTaskRequest,
    SetTaskParentRequest,
    TaskDependencyResponse,
    TaskRelationResponse,
    TaskResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["task-relationships"])


def _task_response(dto) -> TaskResponse:
    return TaskResponse(
        id=dto.id, project_id=dto.project_id, org_id=dto.org_id, title=dto.title, description=dto.description,
        status=dto.status, priority=dto.priority, parent_task_id=dto.parent_task_id, position=dto.position,
        start_date=dto.start_date, due_date=dto.due_date, reminder_date=dto.reminder_date,
        completion_date=dto.completion_date, is_archived=dto.is_archived, archived_at=dto.archived_at,
        is_overdue=dto.is_overdue,
    )


@router.put("/tasks/{task_id}/parent", response_model=DataResponse[TaskResponse])
async def set_task_parent(
    task_id: str,
    request: SetTaskParentRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[TaskResponse]:
    task = await service.set_parent(task_id=UUID(task_id), actor_user_id=claims.subject_user_id, parent_task_id=request.parent_task_id)
    return DataResponse(data=_task_response(task))


@router.get("/tasks/{task_id}/subtasks", response_model=DataResponse[list[TaskResponse]])
async def list_subtasks(
    task_id: str,
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[list[TaskResponse]]:
    subtasks = await service.list_subtasks(parent_task_id=UUID(task_id))
    return DataResponse(data=[_task_response(t) for t in subtasks])


@router.post("/tasks/{task_id}/dependencies", response_model=DataResponse[TaskDependencyResponse], status_code=201)
async def add_dependency(
    task_id: str,
    request: AddDependencyRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[TaskDependencyResponse]:
    dependency = await service.add_dependency(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, depends_on_task_id=request.depends_on_task_id
    )
    return DataResponse(
        data=TaskDependencyResponse(id=dependency.id, task_id=dependency.task_id, depends_on_task_id=dependency.depends_on_task_id)
    )


@router.delete("/tasks/{task_id}/dependencies/{depends_on_task_id}", status_code=204)
async def remove_dependency(
    task_id: str,
    depends_on_task_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> None:
    await service.remove_dependency(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, depends_on_task_id=UUID(depends_on_task_id)
    )


@router.get("/tasks/{task_id}/blocked-by", response_model=DataResponse[list[TaskResponse]])
async def list_blocking_tasks(
    task_id: str,
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[list[TaskResponse]]:
    tasks = await service.list_blocking_tasks(task_id=UUID(task_id))
    return DataResponse(data=[_task_response(t) for t in tasks])


@router.get("/tasks/{task_id}/is-blocked", response_model=DataResponse[bool])
async def is_task_blocked(
    task_id: str,
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[bool]:
    blocked = await service.is_blocked(task_id=UUID(task_id))
    return DataResponse(data=blocked)


@router.post("/tasks/{task_id}/related", response_model=DataResponse[TaskRelationResponse], status_code=201)
async def add_related_task(
    task_id: str,
    request: AddRelatedTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[TaskRelationResponse]:
    relation = await service.add_related_task(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, related_task_id=request.related_task_id
    )
    return DataResponse(data=TaskRelationResponse(id=relation.id, task_id=relation.task_id, related_task_id=relation.related_task_id))


@router.delete("/tasks/{task_id}/related/{related_task_id}", status_code=204)
async def remove_related_task(
    task_id: str,
    related_task_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> None:
    await service.remove_related_task(
        task_id=UUID(task_id), actor_user_id=claims.subject_user_id, related_task_id=UUID(related_task_id)
    )


@router.get("/tasks/{task_id}/related", response_model=DataResponse[list[TaskResponse]])
async def list_related_tasks(
    task_id: str,
    service: TaskRelationshipService = Depends(deps.get_task_relationship_service),
) -> DataResponse[list[TaskResponse]]:
    tasks = await service.list_related_tasks(task_id=UUID(task_id))
    return DataResponse(data=[_task_response(t) for t in tasks])
