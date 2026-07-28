"""Columns HTTP routes: create/rename/delete/reorder, WIP limits, colors, policies."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.boards.application.column_management import ColumnService
from app.boards.presentation import deps
from app.boards.presentation.schemas import (
    BoardColumnResponse,
    CreateColumnRequest,
    RenameColumnRequest,
    ReorderColumnRequest,
    SetColumnColorRequest,
    SetColumnPoliciesRequest,
    SetMappedTaskStatusRequest,
    SetWipLimitRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["boards-columns"])


def _to_response(dto) -> BoardColumnResponse:
    return BoardColumnResponse(
        id=dto.id, board_id=dto.board_id, name=dto.name, position=dto.position, wip_limit=dto.wip_limit,
        color=dto.color, mapped_task_status=dto.mapped_task_status, policies=dto.policies, card_count=dto.card_count,
    )


@router.post("/boards/{board_id}/columns", response_model=DataResponse[BoardColumnResponse], status_code=201)
async def create_column(
    board_id: str,
    request: CreateColumnRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.create_column(
        board_id=UUID(board_id), actor_user_id=claims.subject_user_id, name=request.name, wip_limit=request.wip_limit,
        color=request.color, mapped_task_status=request.mapped_task_status,
    )
    return DataResponse(data=_to_response(column))


@router.get("/boards/{board_id}/columns", response_model=DataResponse[list[BoardColumnResponse]])
async def list_columns(
    board_id: str,
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[list[BoardColumnResponse]]:
    columns = await service.list_for_board(board_id=UUID(board_id))
    return DataResponse(data=[_to_response(c) for c in columns])


@router.patch("/columns/{column_id}", response_model=DataResponse[BoardColumnResponse])
async def rename_column(
    column_id: str,
    request: RenameColumnRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.rename_column(column_id=UUID(column_id), actor_user_id=claims.subject_user_id, name=request.name)
    return DataResponse(data=_to_response(column))


@router.put("/columns/{column_id}/wip-limit", response_model=DataResponse[BoardColumnResponse])
async def set_wip_limit(
    column_id: str,
    request: SetWipLimitRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.set_wip_limit(column_id=UUID(column_id), actor_user_id=claims.subject_user_id, wip_limit=request.wip_limit)
    return DataResponse(data=_to_response(column))


@router.put("/columns/{column_id}/color", response_model=DataResponse[BoardColumnResponse])
async def set_column_color(
    column_id: str,
    request: SetColumnColorRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.set_color(column_id=UUID(column_id), actor_user_id=claims.subject_user_id, color=request.color)
    return DataResponse(data=_to_response(column))


@router.put("/columns/{column_id}/policies", response_model=DataResponse[BoardColumnResponse])
async def set_column_policies(
    column_id: str,
    request: SetColumnPoliciesRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.set_policies(column_id=UUID(column_id), actor_user_id=claims.subject_user_id, policies=request.policies)
    return DataResponse(data=_to_response(column))


@router.put("/columns/{column_id}/mapped-status", response_model=DataResponse[BoardColumnResponse])
async def set_mapped_task_status(
    column_id: str,
    request: SetMappedTaskStatusRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.set_mapped_task_status(column_id=UUID(column_id), actor_user_id=claims.subject_user_id, status=request.status)
    return DataResponse(data=_to_response(column))


@router.post("/columns/{column_id}/reorder", response_model=DataResponse[BoardColumnResponse])
async def reorder_column(
    column_id: str,
    request: ReorderColumnRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> DataResponse[BoardColumnResponse]:
    column = await service.reorder_column(
        column_id=UUID(column_id), actor_user_id=claims.subject_user_id,
        previous_column_id=request.previous_column_id, next_column_id=request.next_column_id,
    )
    return DataResponse(data=_to_response(column))


@router.delete("/columns/{column_id}", status_code=204)
async def delete_column(
    column_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ColumnService = Depends(deps.get_column_service),
) -> None:
    await service.delete_column(column_id=UUID(column_id), actor_user_id=claims.subject_user_id)
