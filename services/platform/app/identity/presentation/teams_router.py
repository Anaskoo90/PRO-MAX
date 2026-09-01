"""Teams HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.identity.application.team_management import TeamService
from app.identity.domain.team import TeamRole
from app.identity.presentation import deps
from app.identity.presentation.authorization import assert_path_org_matches_claims, require_permission
from app.identity.presentation.schemas import (
    AddTeamMemberRequest,
    CreateTeamRequest,
    SetTeamParentRequest,
    TeamMembershipResponse,
    TeamResponse,
    UpdateTeamMemberRoleRequest,
    UpdateTeamRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["teams"])


def _to_response(dto) -> TeamResponse:
    return TeamResponse(id=dto.id, org_id=dto.org_id, name=dto.name, description=dto.description, parent_team_id=dto.parent_team_id)


def _membership_response(dto) -> TeamMembershipResponse:
    return TeamMembershipResponse(id=dto.id, team_id=dto.team_id, user_id=dto.user_id, team_role=dto.team_role)


@router.post(
    "/teams", response_model=DataResponse[TeamResponse], status_code=201,
    dependencies=[Depends(require_permission("team", "create"))],
)
async def create_team(
    request: CreateTeamRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[TeamResponse]:
    team = await service.create_team(
        org_id=claims.org_id, name=request.name, description=request.description, parent_team_id=request.parent_team_id
    )
    return DataResponse(data=_to_response(team))


@router.get("/organizations/{org_id}/teams", response_model=DataResponse[list[TeamResponse]])
async def list_teams(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[list[TeamResponse]]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    teams = await service.list_teams_for_org(org_id=parsed_org_id)
    return DataResponse(data=[_to_response(t) for t in teams])


@router.patch(
    "/teams/{team_id}", response_model=DataResponse[TeamResponse],
    dependencies=[Depends(require_permission("team", "update"))],
)
async def update_team(
    team_id: str,
    request: UpdateTeamRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[TeamResponse]:
    team = await service.update_team(
        org_id=claims.org_id, team_id=UUID(team_id), name=request.name, description=request.description
    )
    return DataResponse(data=_to_response(team))


@router.put(
    "/teams/{team_id}/parent", response_model=DataResponse[TeamResponse],
    dependencies=[Depends(require_permission("team", "update"))],
)
async def set_team_parent(
    team_id: str,
    request: SetTeamParentRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[TeamResponse]:
    team = await service.set_parent(
        org_id=claims.org_id, team_id=UUID(team_id), parent_team_id=request.parent_team_id
    )
    return DataResponse(data=_to_response(team))


@router.delete(
    "/teams/{team_id}", status_code=204,
    dependencies=[Depends(require_permission("team", "delete"))],
)
async def delete_team(
    team_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> None:
    await service.delete_team(org_id=claims.org_id, team_id=UUID(team_id))


@router.post(
    "/teams/{team_id}/members", response_model=DataResponse[TeamMembershipResponse], status_code=201,
    dependencies=[Depends(require_permission("team", "manage_members"))],
)
async def add_team_member(
    team_id: str,
    request: AddTeamMemberRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[TeamMembershipResponse]:
    membership = await service.add_member(
        org_id=claims.org_id, team_id=UUID(team_id), user_id=request.user_id, team_role=TeamRole(request.team_role)
    )
    return DataResponse(data=_membership_response(membership))


@router.get("/teams/{team_id}/members", response_model=DataResponse[list[TeamMembershipResponse]])
async def list_team_members(
    team_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[list[TeamMembershipResponse]]:
    memberships = await service.list_members_for_org(org_id=claims.org_id, team_id=UUID(team_id))
    return DataResponse(data=[_membership_response(m) for m in memberships])


@router.patch(
    "/teams/{team_id}/members/{user_id}", response_model=DataResponse[TeamMembershipResponse],
    dependencies=[Depends(require_permission("team", "manage_members"))],
)
async def update_team_member_role(
    team_id: str,
    user_id: str,
    request: UpdateTeamMemberRoleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> DataResponse[TeamMembershipResponse]:
    membership = await service.update_member_role(
        org_id=claims.org_id, team_id=UUID(team_id), user_id=UUID(user_id), team_role=TeamRole(request.team_role)
    )
    return DataResponse(data=_membership_response(membership))


@router.delete(
    "/teams/{team_id}/members/{user_id}", status_code=204,
    dependencies=[Depends(require_permission("team", "manage_members"))],
)
async def remove_team_member(
    team_id: str,
    user_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TeamService = Depends(deps.get_team_service),
) -> None:
    await service.remove_member(org_id=claims.org_id, team_id=UUID(team_id), user_id=UUID(user_id))
