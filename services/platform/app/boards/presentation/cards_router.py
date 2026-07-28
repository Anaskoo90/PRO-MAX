"""Task Movement HTTP routes: add/remove task to/from board, move between
columns, reorder (drag & drop), batch move; Estimates."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.boards.application.card_movement import CardMovementService
from app.boards.application.estimate_management import EstimateService
from app.boards.domain.entities import EstimateType
from app.boards.presentation import deps
from app.boards.presentation.schemas import (
    AddTaskToBoardRequest,
    BatchMoveRequest,
    BoardCardResponse,
    MoveTaskToColumnRequest,
    ReorderTaskRequest,
    SetEstimateRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["boards-cards"])


def _to_response(dto) -> BoardCardResponse:
    return BoardCardResponse(
        id=dto.id, board_id=dto.board_id, task_id=dto.task_id, column_id=dto.column_id, swimlane_id=dto.swimlane_id,
        sprint_id=dto.sprint_id, position=dto.position, estimate_type=dto.estimate_type, estimate_value=dto.estimate_value,
        custom_estimate_label=dto.custom_estimate_label,
    )


@router.post("/boards/{board_id}/cards", response_model=DataResponse[BoardCardResponse], status_code=201)
async def add_task_to_board(
    board_id: str,
    request: AddTaskToBoardRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: CardMovementService = Depends(deps.get_card_movement_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.add_task_to_board(
        board_id=UUID(board_id), actor_user_id=claims.subject_user_id, task_id=request.task_id, column_id=request.column_id,
    )
    return DataResponse(data=_to_response(card))


@router.get("/boards/{board_id}/cards", response_model=DataResponse[list[BoardCardResponse]])
async def list_cards(
    board_id: str,
    service: CardMovementService = Depends(deps.get_card_movement_service),
) -> DataResponse[list[BoardCardResponse]]:
    cards = await service.list_for_board(board_id=UUID(board_id))
    return DataResponse(data=[_to_response(c) for c in cards])


@router.post("/cards/batch-move", response_model=DataResponse[list[BoardCardResponse]])
async def batch_move_cards(
    request: BatchMoveRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: CardMovementService = Depends(deps.get_card_movement_service),
) -> DataResponse[list[BoardCardResponse]]:
    cards = await service.batch_move(
        actor_user_id=claims.subject_user_id, moves=[(entry.card_id, entry.column_id) for entry in request.moves],
    )
    return DataResponse(data=[_to_response(c) for c in cards])


@router.delete("/cards/{card_id}", status_code=204)
async def remove_task_from_board(
    card_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: CardMovementService = Depends(deps.get_card_movement_service),
) -> None:
    await service.remove_task_from_board(card_id=UUID(card_id), actor_user_id=claims.subject_user_id)


@router.post("/cards/{card_id}/move", response_model=DataResponse[BoardCardResponse])
async def move_task_to_column(
    card_id: str,
    request: MoveTaskToColumnRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: CardMovementService = Depends(deps.get_card_movement_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.move_task_to_column(
        card_id=UUID(card_id), actor_user_id=claims.subject_user_id, column_id=request.column_id,
        previous_card_id=request.previous_card_id, next_card_id=request.next_card_id, swimlane_id=request.swimlane_id,
    )
    return DataResponse(data=_to_response(card))


@router.post("/cards/{card_id}/reorder", response_model=DataResponse[BoardCardResponse])
async def reorder_task(
    card_id: str,
    request: ReorderTaskRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: CardMovementService = Depends(deps.get_card_movement_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.reorder_task(
        card_id=UUID(card_id), actor_user_id=claims.subject_user_id,
        previous_card_id=request.previous_card_id, next_card_id=request.next_card_id,
    )
    return DataResponse(data=_to_response(card))


@router.put("/cards/{card_id}/estimate", response_model=DataResponse[BoardCardResponse])
async def set_estimate(
    card_id: str,
    request: SetEstimateRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: EstimateService = Depends(deps.get_estimate_service),
) -> DataResponse[BoardCardResponse]:
    card = await service.set_estimate(
        card_id=UUID(card_id), actor_user_id=claims.subject_user_id, estimate_type=EstimateType(request.estimate_type),
        value=request.value, custom_label=request.custom_label,
    )
    return DataResponse(data=_to_response(card))
