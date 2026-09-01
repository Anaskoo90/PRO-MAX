"""Roles + Permissions HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.identity.application.rbac_management import PermissionCatalogService, RoleService
from app.identity.presentation import deps
from app.identity.presentation.authorization import assert_path_org_matches_claims, require_permission
from app.identity.presentation.schemas import (
    AssignRoleRequest,
    CreateRoleRequest,
    GrantPermissionRequest,
    PermissionMatrixResponse,
    PermissionResponse,
    RoleResponse,
    SetRoleParentRequest,
    UpdateRoleRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["rbac"])


def _role_response(dto) -> RoleResponse:
    return RoleResponse(
        id=dto.id, org_id=dto.org_id, name=dto.name, description=dto.description, is_system_role=dto.is_system_role,
        parent_role_id=dto.parent_role_id, permission_ids=dto.permission_ids,
    )


@router.get("/permissions", response_model=DataResponse[list[PermissionResponse]])
async def list_permission_catalog(
    service: PermissionCatalogService = Depends(deps.get_permission_catalog_service),
) -> DataResponse[list[PermissionResponse]]:
    permissions = await service.list_catalog()
    return DataResponse(
        data=[PermissionResponse(id=p.id, resource=p.resource, action=p.action, description=p.description) for p in permissions]
    )


@router.get(
    "/organizations/{org_id}/roles", response_model=DataResponse[list[RoleResponse]],
    dependencies=[Depends(require_permission("role", "read"))],
)
async def list_roles(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[list[RoleResponse]]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    roles = await service.list_roles_for_org(org_id=parsed_org_id)
    return DataResponse(data=[_role_response(r) for r in roles])


@router.get(
    "/organizations/{org_id}/permission-matrix", response_model=DataResponse[PermissionMatrixResponse],
    dependencies=[Depends(require_permission("role", "read"))],
)
async def get_permission_matrix(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    role_service: RoleService = Depends(deps.get_role_service),
    permission_catalog: PermissionCatalogService = Depends(deps.get_permission_catalog_service),
) -> DataResponse[PermissionMatrixResponse]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    roles = await role_service.list_roles_for_org(org_id=parsed_org_id)
    permissions = await permission_catalog.list_catalog()
    return DataResponse(
        data=PermissionMatrixResponse(
            permissions=[
                PermissionResponse(id=p.id, resource=p.resource, action=p.action, description=p.description)
                for p in permissions
            ],
            roles=[_role_response(r) for r in roles],
        )
    )


@router.get(
    "/organizations/{org_id}/members/{user_id}/roles", response_model=DataResponse[list[RoleResponse]],
    dependencies=[Depends(require_permission("role", "read"))],
)
async def list_roles_for_member(
    org_id: str,
    user_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[list[RoleResponse]]:
    parsed_org_id = assert_path_org_matches_claims(org_id, claims)
    roles = await service.list_roles_for_user(user_id=UUID(user_id), org_id=parsed_org_id)
    return DataResponse(data=[_role_response(r) for r in roles])


@router.post(
    "/roles", response_model=DataResponse[RoleResponse], status_code=201,
    dependencies=[Depends(require_permission("role", "create"))],
)
async def create_role(
    request: CreateRoleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[RoleResponse]:
    role = await service.create_custom_role(
        org_id=claims.org_id, name=request.name, description=request.description, actor_user_id=claims.subject_user_id
    )
    return DataResponse(data=_role_response(role))


@router.patch(
    "/roles/{role_id}", response_model=DataResponse[RoleResponse],
    dependencies=[Depends(require_permission("role", "update"))],
)
async def update_role(
    role_id: str,
    request: UpdateRoleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[RoleResponse]:
    role = await service.update_role(role_id=UUID(role_id), name=request.name, actor_user_id=claims.subject_user_id)
    return DataResponse(data=_role_response(role))


@router.put(
    "/roles/{role_id}/parent", response_model=DataResponse[RoleResponse],
    dependencies=[Depends(require_permission("role", "update"))],
)
async def set_role_parent(
    role_id: str,
    request: SetRoleParentRequest,
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[RoleResponse]:
    role = await service.set_parent(role_id=UUID(role_id), parent_role_id=request.parent_role_id)
    return DataResponse(data=_role_response(role))


@router.delete(
    "/roles/{role_id}", status_code=204,
    dependencies=[Depends(require_permission("role", "delete"))],
)
async def delete_role(
    role_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> None:
    await service.delete_role(role_id=UUID(role_id), actor_user_id=claims.subject_user_id)


@router.post(
    "/roles/{role_id}/permissions", response_model=DataResponse[RoleResponse],
    dependencies=[Depends(require_permission("permission", "assign"))],
)
async def grant_permission(
    role_id: str,
    request: GrantPermissionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[RoleResponse]:
    role = await service.grant_permission(
        role_id=UUID(role_id), permission_id=request.permission_id, actor_user_id=claims.subject_user_id
    )
    return DataResponse(data=_role_response(role))


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}", response_model=DataResponse[RoleResponse],
    dependencies=[Depends(require_permission("permission", "assign"))],
)
async def revoke_permission(
    role_id: str,
    permission_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> DataResponse[RoleResponse]:
    role = await service.revoke_permission(
        role_id=UUID(role_id), permission_id=UUID(permission_id), actor_user_id=claims.subject_user_id
    )
    return DataResponse(data=_role_response(role))


@router.post(
    "/roles/assign", status_code=204,
    dependencies=[Depends(require_permission("role", "assign"))],
)
async def assign_role(
    request: AssignRoleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> None:
    await service.assign_role_to_user(
        user_id=request.user_id, role_id=request.role_id, org_id=claims.org_id, actor_user_id=claims.subject_user_id
    )


@router.post(
    "/roles/revoke", status_code=204,
    dependencies=[Depends(require_permission("role", "assign"))],
)
async def revoke_role(
    request: AssignRoleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: RoleService = Depends(deps.get_role_service),
) -> None:
    await service.revoke_role_from_user(
        user_id=request.user_id, role_id=request.role_id, org_id=claims.org_id, actor_user_id=claims.subject_user_id
    )
