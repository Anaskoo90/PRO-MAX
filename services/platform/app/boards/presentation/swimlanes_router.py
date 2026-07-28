"""Swimlanes HTTP routes: CUSTOM swimlane CRUD/reorder, plus the dynamic
groups endpoint for ASSIGNEE/PRIORITY/LABEL/PROJECT/EPIC strategies."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.boards.application.swimlane_management import SwimlaneService
from app.boards.presentation import deps
from app.boards.presentation.schemas import (
    CreateSwimlaneRequest,
    RenameSwimlaneRequest,
    ReorderSwimlaneRequest,
    SwimlaneGroupResponse,
    SwimlaneResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["boards-swimlanes"])


def _to_response(dto) -> SwimlaneResponse:
    return SwimlaneResponse(id=dto.id, board_id=dto.board_id, name=dto.name, position=dto.position)


@router.post("/boards/{board_id}/swimlanes", response_model=DataResponse[SwimlaneResponse], status_code=201)
async def create_swimlane(
    board_id: str,
    request: CreateSwimlaneRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SwimlaneService = Depends(deps.get_swimlane_service),
) -> DataResponse[SwimlaneResponse]:
    swimlane = await service.create_swimlane(board_id=UUID(board_id), actor_user_id=claims.subject_user_id, name=request.name)
    return DataResponse(data=_to_response(swimlane))


@router.get("/boards/{board_id}/swimlanes", response_model=DataResponse[list[SwimlaneResponse]])
async def list_swimlanes(
    board_id: str,
    service: SwimlaneService = Depends(deps.get_swimlane_service),
) -> DataResponse[list[SwimlaneResponse]]:
    swimlanes = await service.list_for_board(board_id=UUID(board_id))
    return DataResponse(data=[_to_response(s) for s in swimlanes])


@router.get("/boards/{board_id}/swimlanes/dynamic-groups", response_model=DataResponse[list[SwimlaneGroupResponse]])
async def get_dynamic_swimlane_groups(
    board_id: str,
    service: SwimlaneService = Depends(deps.get_swimlane_service),
) -> DataResponse[list[SwimlaneGroupResponse]]:
    groups = await service.compute_dynamic_groups(board_id=UUID(board_id))
    return DataResponse(data=[SwimlaneGroupResponse(key=g.key, label=g.label, card_ids=g.card_ids) for g in groups])


@router.patch("/swimlanes/{swimlane_id}", response_model=DataResponse[SwimlaneResponse])
async def rename_swimlane(
    swimlane_id: str,
    request: RenameSwimlaneRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SwimlaneService = Depends(deps.get_swimlane_service),
) -> DataResponse[SwimlaneResponse]:
    swimlane = await service.rename_swimlane(swimlane_id=UUID(swimlane_id), actor_user_id=claims.subject_user_id, name=request.name)
    return DataResponse(data=_to_response(swimlane))


@router.post("/swimlanes/{swimlane_id}/reorder", response_model=DataResponse[SwimlaneResponse])
async def reorder_swimlane(
    swimlane_id: str,
    request: ReorderSwimlaneRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SwimlaneService = Depends(deps.get_swimlane_service),
) -> DataResponse[SwimlaneResponse]:
    swimlane = await service.reorder_swimlane(
        swimlane_id=UUID(swimlane_id), actor_user_id=claims.subject_user_id,
        previous_swimlane_id=request.previous_swimlane_id, next_swimlane_id=request.next_swimlane_id,
    )
    return DataResponse(data=_to_response(swimlane))


@router.delete("/swimlanes/{swimlane_id}", status_code=204)
async def delete_swimlane(
    swimlane_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SwimlaneService = Depends(deps.get_swimlane_service),
) -> None:
    await service.delete_swimlane(swimlane_id=UUID(swimlane_id), actor_user_id=claims.subject_user_id)
