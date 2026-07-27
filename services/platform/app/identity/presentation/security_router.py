"""Security submodule HTTP routes: device trust + audit log query."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request

from app.identity.application.security import AuditLogQueryService, SecurityService, fingerprint_device
from app.identity.domain.audit import AuditEventCategory
from app.identity.presentation import deps
from app.identity.presentation.authorization import require_permission
from app.identity.presentation.schemas import AuditLogResponse, TrustDeviceRequest, TrustedDeviceResponse
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["security"])


@router.post("/users/me/trusted-devices", status_code=204)
async def trust_current_device(
    request: TrustDeviceRequest,
    http_request: Request,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SecurityService = Depends(deps.get_security_service),
) -> None:
    fingerprint_hash = fingerprint_device(
        user_agent=http_request.headers.get("user-agent", ""),
        accept_language=http_request.headers.get("accept-language", ""),
    )
    await service.device_trust_service.trust_device(
        user_id=claims.subject_user_id, fingerprint_hash=fingerprint_hash, label=request.label
    )


@router.get("/users/me/trusted-devices", response_model=DataResponse[list[TrustedDeviceResponse]])
async def list_trusted_devices(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: SecurityService = Depends(deps.get_security_service),
) -> DataResponse[list[TrustedDeviceResponse]]:
    devices = await service.device_trust_service.list_trusted_devices(user_id=claims.subject_user_id)
    return DataResponse(
        data=[TrustedDeviceResponse(id=d.id, label=d.label, trusted_until=d.trusted_until) for d in devices]
    )


@router.delete("/users/me/trusted-devices/{device_id}", status_code=204)
async def revoke_trusted_device(
    device_id: str,
    service: SecurityService = Depends(deps.get_security_service),
) -> None:
    await service.device_trust_service.revoke_device(device_id=UUID(device_id))


@router.get(
    "/organizations/{org_id}/audit-logs", response_model=DataResponse[list[AuditLogResponse]],
    dependencies=[Depends(require_permission("audit_log", "read"))],
)
async def list_audit_logs(
    org_id: str,
    category: AuditEventCategory | None = None,
    limit: int = 50,
    service: AuditLogQueryService = Depends(deps.get_audit_log_query_service),
) -> DataResponse[list[AuditLogResponse]]:
    records = await service.list_for_org(org_id=UUID(org_id), category=category, limit=limit)
    return DataResponse(
        data=[
            AuditLogResponse(
                id=r.id, org_id=r.org_id, category=r.category.value, action=r.action, actor_user_id=r.actor_user_id,
                resource_type=r.resource_type, resource_id=r.resource_id, ip_address=r.ip_address,
                metadata=r.metadata, occurred_at=r.occurred_at,
            )
            for r in records
        ]
    )
