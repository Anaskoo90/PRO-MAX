"""Organization Invitations HTTP routes."""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.organization_invitations import OrganizationInvitationService
from app.identity.presentation import deps
from app.identity.presentation.authorization import require_permission
from app.identity.presentation.schemas import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    InvitationResponse,
    UserProfileResponse,
)
from app.platform_core.api.pagination import PageParams, page_params
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["organization-invitations"])


def _to_response(dto) -> InvitationResponse:
    return InvitationResponse(
        id=dto.id,
        org_id=dto.org_id,
        email=dto.email,
        role_id=dto.role_id,
        invited_by_user_id=dto.invited_by_user_id,
        status=dto.status,
        created_at=dto.created_at,
        expires_at=dto.expires_at,
    )


@router.post(
    "/organizations/{org_id}/invitations",
    response_model=DataResponse[InvitationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("organization", "invite_member"))],
)
async def create_invitation(
    org_id: str,
    request: CreateInvitationRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationInvitationService = Depends(deps.get_organization_invitation_service),
) -> DataResponse[InvitationResponse]:
    from uuid import UUID

    invitation = await service.invite_member(
        org_id=UUID(org_id), email=request.email, role_id=request.role_id, invited_by_user_id=claims.subject_user_id
    )
    return DataResponse(data=_to_response(invitation))


@router.get(
    "/organizations/{org_id}/invitations",
    response_model=DataResponse[list[InvitationResponse]],
    dependencies=[Depends(require_permission("organization", "invite_member"))],
)
async def list_pending_invitations(
    org_id: str,
    page: PageParams = Depends(page_params),
    service: OrganizationInvitationService = Depends(deps.get_organization_invitation_service),
) -> DataResponse[list[InvitationResponse]]:
    from uuid import UUID

    invitations = await service.list_pending(org_id=UUID(org_id), offset=page.offset, limit=page.limit)
    return DataResponse(data=[_to_response(i) for i in invitations])


@router.delete(
    "/organizations/{org_id}/invitations/{invitation_id}",
    status_code=204,
    dependencies=[Depends(require_permission("organization", "invite_member"))],
)
async def revoke_invitation(
    org_id: str,
    invitation_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationInvitationService = Depends(deps.get_organization_invitation_service),
) -> None:
    from uuid import UUID

    await service.revoke_invitation(
        org_id=UUID(org_id), invitation_id=UUID(invitation_id), actor_user_id=claims.subject_user_id
    )


@router.post(
    "/invitations/accept",
    response_model=DataResponse[UserProfileResponse],
    status_code=201,
)
async def accept_invitation(
    request: AcceptInvitationRequest,
    service: OrganizationInvitationService = Depends(deps.get_organization_invitation_service),
) -> DataResponse[UserProfileResponse]:
    """Unauthenticated: the invitee has no account yet — the raw token
    (proof of email ownership, mailed by create_invitation) is the only
    credential required, matching reset_password/verify_email's pattern of
    a public, token-authenticated endpoint."""
    profile = await service.accept_invitation(
        raw_token=request.token, password=request.password, display_name=request.display_name
    )
    return DataResponse(
        data=UserProfileResponse(
            id=profile.id,
            org_id=profile.org_id,
            email=profile.email,
            display_name=profile.display_name,
            status=profile.status,
            mfa_enabled=profile.mfa_enabled,
            avatar_storage_key=profile.avatar_storage_key,
            preferences=profile.preferences,
        )
    )
