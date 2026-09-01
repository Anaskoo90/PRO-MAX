"""Organization Management HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.identity.application.organization_management import OrganizationManagementService
from app.identity.presentation import deps
from app.identity.presentation.authorization import assert_path_org_matches_claims, require_permission
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
from app.platform_core.api.sorting import UnsortableFieldError, parse_sort
from app.platform_core.api.versioning import versioned_router
from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["organizations"])

# The only fields OrganizationManagementService.search_members's underlying
# repository query knows how to sort on (see infrastructure/repositories.py's
# _USER_SORTABLE_COLUMNS) — kept in lockstep with that set.
_MEMBER_SORT_FIELDS = {"created_at", "display_name", "email"}


def _to_response(dto) -> OrganizationResponse:
    return OrganizationResponse(
        id=dto.id, name=dto.name, slug=dto.slug, owner_user_id=dto.owner_user_id, status=dto.status,
        settings=dto.settings, description=dto.description, logo_url=dto.logo_url,
    )


def _to_member_response(dto) -> UserProfileResponse:
    return UserProfileResponse(
        id=dto.id, org_id=dto.org_id, email=dto.email, display_name=dto.display_name, status=dto.status,
        mfa_enabled=dto.mfa_enabled, avatar_storage_key=dto.avatar_storage_key, preferences=dto.preferences,
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
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[OrganizationResponse]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    org = await service.get(org_id=parsed_org_id)
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
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    org = await service.update(
        org_id=parsed_org_id, name=request.name, actor_user_id=claims.subject_user_id,
        slug=request.slug, description=request.description, logo_url=request.logo_url,
    )
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
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    org = await service.update_settings(org_id=parsed_org_id, patch=request.settings, actor_user_id=claims.subject_user_id)
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
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    org = await service.transfer_ownership(
        org_id=parsed_org_id, new_owner_user_id=request.new_owner_user_id, actor_user_id=claims.subject_user_id
    )
    return DataResponse(data=_to_response(org))


@router.get(
    "/organizations/{org_id}/members",
    response_model=PagedResponse[UserProfileResponse],
    dependencies=[Depends(require_permission("user", "read"))],
)
async def list_organization_members(
    org_id: str,
    page: PageParams = Depends(page_params),
    q: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> PagedResponse[UserProfileResponse]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    try:
        sort_fields = parse_sort(sort, _MEMBER_SORT_FIELDS)
    except UnsortableFieldError as exc:
        raise BusinessRuleViolationError("unsortable_field", str(exc)) from exc

    result = await service.search_members(
        org_id=parsed_org_id, query=q, status=status, sort=sort_fields, page=page.page, page_size=page.page_size,
    )
    return PagedResponse(
        data=[_to_member_response(dto) for dto in result.items], page=result.page, page_size=result.page_size,
        total=result.total, total_pages=result.total_pages,
    )


@router.get(
    "/organizations/{org_id}/members/{user_id}",
    response_model=DataResponse[UserProfileResponse],
    dependencies=[Depends(require_permission("user", "read"))],
)
async def get_organization_member(
    org_id: str,
    user_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: OrganizationManagementService = Depends(deps.get_organization_management_service),
) -> DataResponse[UserProfileResponse]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    member = await service.get_member(org_id=parsed_org_id, user_id=UUID(user_id))
    return DataResponse(data=_to_member_response(member))


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
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    org = await service.suspend(org_id=parsed_org_id, actor_user_id=claims.subject_user_id)
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
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    org = await service.reactivate(org_id=parsed_org_id, actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(org))
