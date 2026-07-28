"""Backlog HTTP routes: product backlog, sprint backlog, move between
backlog and board/sprint."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.boards.application.backlog_management import BacklogService
from app.boards.presentation import deps
from app.boards.presentation.schemas import AssignToSprintRequest, BoardCardResponse
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["boards-backlog"])


def _to_response(dto) -> BoardCardResponse:
    return BoardCardResponse(
        id=dto.id, board_id=dto.board_id, task_id=dto.task_id, column_id=dto.column_id, swimlane_id=dto.swimlane_id,
        sprint_id=dto.sprint_id, position=dto.position, estimate_type=dto.estimate_type, estimate_value=dto.estimate_value,
        custom_estimate_label=dto.custom_estimate_label,
    )


@router.get("/boards/{board_id}/backlog", response_model=DataResponse[list[BoardCardResponse]])
async def get_product_backlog(
    board_id: str,
    service: BacklogService = Depends(deps.get_backlog_service),
) -> DataResponse[list[BoardCardResponse]]:
    cards = await service.list_product_backlog(board_id=UUID(board_id))
    return DataResponse(data=[_to_response(c) for c in cards])


@router.get("/sprints/{sprint_id}/backlog", response_model=DataResponse[list[BoardCardResponse]])
async def get_sprint_backlog(
    sprint_id: str,
    service: BacklogService = Depends(deps.get_backlog_service),
) -> DataResponse[list[BoardCardResponse]]:
    cards = await service.list_sprint_backlog(sprint_id=UUID(sprint_id))
    return DataResponse(data=[_to_response(c) for c in cards])


@router.post("/cards/{card_id}/move-to-backlog", response_model=DataResponse[BoardCardResponse])
async def move_to_backlog(
    card_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BacklogService = Depends(deps.get_backlog_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.move_to_backlog(card_id=UUID(card_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(card))


@router.post("/cards/{card_id}/assign-to-sprint", response_model=DataResponse[BoardCardResponse])
async def assign_to_sprint(
    card_id: str,
    request: AssignToSprintRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BacklogService = Depends(deps.get_backlog_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.assign_to_sprint(card_id=UUID(card_id), actor_user_id=claims.subject_user_id, sprint_id=request.sprint_id)
    return DataResponse(data=_to_response(card))


@router.post("/cards/{card_id}/remove-from-sprint", response_model=DataResponse[BoardCardResponse])
async def remove_from_sprint(
    card_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BacklogService = Depends(deps.get_backlog_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.remove_from_sprint(card_id=UUID(card_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(card))
