"""Board Aggregate + Board Types HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.boards.application.board_management import BoardService
from app.boards.domain.entities import BoardType, SwimlaneStrategy
from app.boards.presentation import deps
from app.boards.presentation.schemas import (
    BoardResponse,
    ChangeSwimlaneStrategyRequest,
    CreateBoardRequest,
    UpdateBoardRequest,
    UpdateBoardSettingsRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["boards"])


def _to_response(dto) -> BoardResponse:
    return BoardResponse(
        id=dto.id, project_id=dto.project_id, org_id=dto.org_id, name=dto.name, description=dto.description,
        board_type=dto.board_type, swimlane_strategy=dto.swimlane_strategy, status=dto.status, settings=dto.settings,
        archived_at=dto.archived_at,
    )


@router.post("/projects/{project_id}/boards", response_model=DataResponse[BoardResponse], status_code=201)
async def create_board(
    project_id: str,
    request: CreateBoardRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.create_board(
        project_id=UUID(project_id), org_id=claims.org_id, actor_user_id=claims.subject_user_id, name=request.name,
        description=request.description, board_type=BoardType(request.board_type),
        swimlane_strategy=SwimlaneStrategy(request.swimlane_strategy),
    )
    return DataResponse(data=_to_response(board))


@router.get("/projects/{project_id}/boards", response_model=DataResponse[list[BoardResponse]])
async def list_boards(
    project_id: str,
    include_archived: bool = False,
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[list[BoardResponse]]:
    boards = await service.list_for_project(project_id=UUID(project_id), include_archived=include_archived)
    return DataResponse(data=[_to_response(b) for b in boards])


@router.get("/boards/{board_id}", response_model=DataResponse[BoardResponse])
async def get_board(
    board_id: str,
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.get(board_id=UUID(board_id))
    return DataResponse(data=_to_response(board))


@router.patch("/boards/{board_id}", response_model=DataResponse[BoardResponse])
async def update_board(
    board_id: str,
    request: UpdateBoardRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.update(board_id=UUID(board_id), actor_user_id=claims.subject_user_id, name=request.name, description=request.description)
    return DataResponse(data=_to_response(board))


@router.put("/boards/{board_id}/settings", response_model=DataResponse[BoardResponse])
async def update_board_settings(
    board_id: str,
    request: UpdateBoardSettingsRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.update_settings(board_id=UUID(board_id), actor_user_id=claims.subject_user_id, patch=request.patch)
    return DataResponse(data=_to_response(board))


@router.post("/boards/{board_id}/swimlane-strategy", response_model=DataResponse[BoardResponse])
async def change_swimlane_strategy(
    board_id: str,
    request: ChangeSwimlaneStrategyRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.change_swimlane_strategy(board_id=UUID(board_id), actor_user_id=claims.subject_user_id, strategy=SwimlaneStrategy(request.strategy))
    return DataResponse(data=_to_response(board))


@router.post("/boards/{board_id}/archive", response_model=DataResponse[BoardResponse])
async def archive_board(
    board_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.archive(board_id=UUID(board_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(board))


@router.post("/boards/{board_id}/restore", response_model=DataResponse[BoardResponse])
async def restore_board(
    board_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BoardResponse]:
    board = await service.restore(board_id=UUID(board_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(board))


@router.delete("/boards/{board_id}", status_code=204)
async def delete_board(
    board_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: BoardService = Depends(deps.get_board_service),
) -> None:
    await service.delete(board_id=UUID(board_id), actor_user_id=claims.subject_user_id)
