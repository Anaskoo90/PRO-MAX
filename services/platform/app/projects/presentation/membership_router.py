"""Membership HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.projects.application.membership_management import ProjectMembershipService
from app.projects.domain.entities import ProjectRole
from app.projects.presentation import deps
from app.projects.presentation.schemas import (
    ChangeProjectMemberRoleRequest,
    InviteProjectMemberRequest,
    ProjectMembershipResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["project-members"])


def _to_response(dto) -> ProjectMembershipResponse:
    return ProjectMembershipResponse(
        id=dto.id, project_id=dto.project_id, user_id=dto.user_id, role=dto.role, status=dto.status,
        invited_by=dto.invited_by, invited_at=dto.invited_at, joined_at=dto.joined_at,
    )


@router.post("/projects/{project_id}/members/invite", response_model=DataResponse[ProjectMembershipResponse], status_code=201)
async def invite_project_member(
    project_id: str,
    request: InviteProjectMemberRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectMembershipService = Depends(deps.get_project_membership_service),
) -> DataResponse[ProjectMembershipResponse]:
    membership = await service.invite_member_by_email(
        project_id=UUID(project_id), actor_user_id=claims.subject_user_id, email=request.email,
        role=ProjectRole(request.role),
    )
    return DataResponse(data=_to_response(membership))


@router.post("/projects/{project_id}/members/accept", response_model=DataResponse[ProjectMembershipResponse])
async def accept_project_invite(
    project_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectMembershipService = Depends(deps.get_project_membership_service),
) -> DataResponse[ProjectMembershipResponse]:
    membership = await service.accept_invite(project_id=UUID(project_id), user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(membership))


@router.get("/projects/{project_id}/members", response_model=DataResponse[list[ProjectMembershipResponse]])
async def list_project_members(
    project_id: str,
    service: ProjectMembershipService = Depends(deps.get_project_membership_service),
) -> DataResponse[list[ProjectMembershipResponse]]:
    memberships = await service.list_members(project_id=UUID(project_id))
    return DataResponse(data=[_to_response(m) for m in memberships])


@router.patch("/projects/{project_id}/members/{user_id}", response_model=DataResponse[ProjectMembershipResponse])
async def change_project_member_role(
    project_id: str,
    user_id: str,
    request: ChangeProjectMemberRoleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectMembershipService = Depends(deps.get_project_membership_service),
) -> DataResponse[ProjectMembershipResponse]:
    membership = await service.change_member_role(
        project_id=UUID(project_id), actor_user_id=claims.subject_user_id, target_user_id=UUID(user_id),
        role=ProjectRole(request.role),
    )
    return DataResponse(data=_to_response(membership))


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
async def remove_project_member(
    project_id: str,
    user_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: ProjectMembershipService = Depends(deps.get_project_membership_service),
) -> None:
    await service.remove_member(project_id=UUID(project_id), actor_user_id=claims.subject_user_id, target_user_id=UUID(user_id))
