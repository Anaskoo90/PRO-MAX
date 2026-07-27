"""Organization Management HTTP routes."""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.organization_management import OrganizationManagementService
from app.identity.presentation import deps
from app.identity.presentation.authorization import require_permission
from app.identity.presentation.schemas import (
    OrganizationResponse,
    RegisterOrganizationRequest,
    TransferOwnershipRequest,
    UpdateOrganizationRequest,
    UpdateOrganizationSettingsRequest,
    UserProfileResponse,
)
from app.platform_core.api.pagination import PageParams, page_params
from app.platform_core.api.responses import DataResponse, PagedResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["organizations"])


def _to_response(dto) -> OrganizationResponse:
    return OrganizationResponse(
        id=dto.id, name=dto.name, slug=dto.slug, owner_user_id=dto.owner_user_id, status=dto.status,
        settings=dto.settings,
    )


@router.post("/organizations/register", response_model=DataResponse[OrganizationResponse], status_code=201)
async def register_organization(
    request: RegisterOrganizationRequest,
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    """The platform's only organization-creation entry point — see
    OrganizationManagementService's module docstring for why this also
    creates the owning user, rather than requiring one to already exist."""
    org_dto, _owner_user_id = await service.register_organization_with_owner(
        org_name=request.org_name,
        slug=request.slug,
        owner_email=request.owner_email,
        owner_password=request.owner_password,
        owner_display_name=request.owner_display_name,
    )
    return DataResponse(data=_to_response(org_dto))


@router.get("/organizations/{org_id}", response_model=DataResponse[OrganizationResponse])
async def get_organization(
    org_id: str,
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    from uuid import UUID

    org = await service.get(org_id=UUID(org_id))
    return DataResponse(data=_to_response(org))


@router.patch(
    "/organizations/{org_id}",
    response_model=DataResponse[OrganizationResponse],
    dependencies=[Depends(require_permission("organization", "update"))],
)
async def update_organization(
    org_id: str,
    request: UpdateOrganizationRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    from uuid import UUID

    org = await service.update(org_id=UUID(org_id), name=request.name, actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(org))


@router.put(
    "/organizations/{org_id}/settings",
    response_model=DataResponse[OrganizationResponse],
    dependencies=[Depends(require_permission("organization", "update"))],
)
async def update_organization_settings(
    org_id: str,
    request: UpdateOrganizationSettingsRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    from uuid import UUID

    org = await service.update_settings(org_id=UUID(org_id), patch=request.settings, actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(org))


@router.post(
    "/organizations/{org_id}/transfer-ownership",
    response_model=DataResponse[OrganizationResponse],
    dependencies=[Depends(require_permission("organization", "manage_ownership"))],
)
async def transfer_ownership(
    org_id: str,
    request: TransferOwnershipRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    from uuid import UUID

    org = await service.transfer_ownership(
        org_id=UUID(org_id), new_owner_user_id=request.new_owner_user_id, actor_user_id=claims.subject_user_id
    )
    return DataResponse(data=_to_response(org))


@router.get(
    "/organizations/{org_id}/members",
    response_model=DataResponse[list[UserProfileResponse]],
    dependencies=[Depends(require_permission("user", "read"))],
)
async def list_organization_members(
    org_id: str,
    page: PageParams = Depends(page_params),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[list[UserProfileResponse]]:
    from uuid import UUID

    members = await service.list_members(org_id=UUID(org_id), offset=page.offset, limit=page.limit)
    return DataResponse(
        data=[
            UserProfileResponse(
                id=m.id, org_id=m.org_id, email=str(m.email), display_name=m.display_name, status=m.status.value,
                mfa_enabled=m.mfa_enabled, avatar_storage_key=m.avatar_storage_key, preferences=m.preferences,
            )
            for m in members
        ]
    )


@router.post(
    "/organizations/{org_id}/suspend",
    response_model=DataResponse[OrganizationResponse],
    dependencies=[Depends(require_permission("organization", "manage_status"))],
)
async def suspend_organization(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    from uuid import UUID

    org = await service.suspend(org_id=UUID(org_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(org))


@router.post(
    "/organizations/{org_id}/reactivate",
    response_model=DataResponse[OrganizationResponse],
    dependencies=[Depends(require_permission("organization", "manage_status"))],
)
async def reactivate_organization(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    from uuid import UUID

    org = await service.reactivate(org_id=UUID(org_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(org))
