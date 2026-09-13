"""Sprint Management HTTP routes: create/start/complete/cancel, goal,
capacity, velocity, burn-down."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.boards.application.sprint_management import SprintService
from app.boards.application.board_management import BoardService
from app.boards.application.sprint_reporting import SprintReportingService
from app.boards.presentation import deps
from app.boards.presentation.schemas import (
    BurndownReportResponse,
    BurndownSnapshotResponse,
    CreateSprintRequest,
    SprintResponse,
    SprintVelocityResponse,
    UpdateSprintRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["boards-sprints"])


def _to_response(dto) -> SprintResponse:
    return SprintResponse(
        id=dto.id, board_id=dto.board_id, name=dto.name, goal=dto.goal, status=dto.status,
        start_date=dto.start_date, end_date=dto.end_date, capacity=dto.capacity,
    )


@router.post("/boards/{board_id}/sprints", response_model=DataResponse[SprintResponse], status_code=201)
async def create_sprint(
    board_id: str,
    request: CreateSprintRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintResponse]:
    await access_service.assert_board_belongs_to_org(board_id=UUID(board_id), org_id=claims.org_id)
    sprint = await service.create_sprint(
        board_id=UUID(board_id), actor_user_id=claims.subject_user_id, name=request.name, goal=request.goal,
        start_date=request.start_date, end_date=request.end_date, capacity=request.capacity,
    )
    return DataResponse(data=_to_response(sprint))


@router.get("/boards/{board_id}/sprints", response_model=DataResponse[list[SprintResponse]])
async def list_sprints(
    board_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[list[SprintResponse]]:
    await access_service.assert_can_view_board(
        board_id=UUID(board_id), org_id=claims.org_id, user_id=claims.subject_user_id
    )
    sprints = await service.list_for_board(board_id=UUID(board_id))
    return DataResponse(data=[_to_response(s) for s in sprints])


@router.get("/sprints/{sprint_id}", response_model=DataResponse[SprintResponse])
async def get_sprint(
    sprint_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintResponse]:
    await access_service.assert_can_view_sprint(
        sprint_id=UUID(sprint_id), org_id=claims.org_id, user_id=claims.subject_user_id
    )
    sprint = await service.get(sprint_id=UUID(sprint_id))
    return DataResponse(data=_to_response(sprint))


@router.patch("/sprints/{sprint_id}", response_model=DataResponse[SprintResponse])
async def update_sprint(
    sprint_id: str,
    request: UpdateSprintRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintResponse]:
    await access_service.assert_sprint_belongs_to_org(sprint_id=UUID(sprint_id), org_id=claims.org_id)
    sprint = await service.update(
        sprint_id=UUID(sprint_id), actor_user_id=claims.subject_user_id, name=request.name, goal=request.goal,
        start_date=request.start_date, end_date=request.end_date, capacity=request.capacity,
    )
    return DataResponse(data=_to_response(sprint))


@router.post("/sprints/{sprint_id}/start", response_model=DataResponse[SprintResponse])
async def start_sprint(
    sprint_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintResponse]:
    await access_service.assert_sprint_belongs_to_org(sprint_id=UUID(sprint_id), org_id=claims.org_id)
    sprint = await service.start_sprint(sprint_id=UUID(sprint_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(sprint))


@router.post("/sprints/{sprint_id}/complete", response_model=DataResponse[SprintResponse])
async def complete_sprint(
    sprint_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintResponse]:
    await access_service.assert_sprint_belongs_to_org(sprint_id=UUID(sprint_id), org_id=claims.org_id)
    sprint = await service.complete_sprint(sprint_id=UUID(sprint_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(sprint))


@router.post("/sprints/{sprint_id}/cancel", response_model=DataResponse[SprintResponse])
async def cancel_sprint(
    sprint_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintResponse]:
    await access_service.assert_sprint_belongs_to_org(sprint_id=UUID(sprint_id), org_id=claims.org_id)
    sprint = await service.cancel_sprint(sprint_id=UUID(sprint_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(sprint))


@router.get("/sprints/{sprint_id}/velocity", response_model=DataResponse[SprintVelocityResponse])
async def get_sprint_velocity(
    sprint_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintService = Depends(deps.get_sprint_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[SprintVelocityResponse]:
    await access_service.assert_can_view_sprint(
        sprint_id=UUID(sprint_id), org_id=claims.org_id, user_id=claims.subject_user_id
    )
    velocity = await service.get_velocity(sprint_id=UUID(sprint_id))
    return DataResponse(data=SprintVelocityResponse(sprint_id=UUID(sprint_id), velocity=velocity))


@router.get("/sprints/{sprint_id}/burndown", response_model=DataResponse[BurndownReportResponse])
async def get_sprint_burndown(
    sprint_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SprintReportingService = Depends(deps.get_sprint_reporting_service),
    access_service: BoardService = Depends(deps.get_board_service),
) -> DataResponse[BurndownReportResponse]:
    await access_service.assert_can_view_sprint(
        sprint_id=UUID(sprint_id), org_id=claims.org_id, user_id=claims.subject_user_id
    )
    report = await service.get_burndown(sprint_id=UUID(sprint_id))
    return DataResponse(
        data=BurndownReportResponse(
            sprint_id=report.sprint_id, capacity=report.capacity,
            snapshots=[BurndownSnapshotResponse(snapshot_date=s.snapshot_date, remaining_points=s.remaining_points, remaining_hours=s.remaining_hours) for s in report.snapshots],
            ideal_remaining_by_day=report.ideal_remaining_by_day,
        )
    )
