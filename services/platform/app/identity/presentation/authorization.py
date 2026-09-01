"""Authorization Middleware: FastAPI dependency factory enforcing RBAC
permissions on a route. Usage:

    @router.post("/teams", dependencies=[Depends(require_permission("team", "create"))])
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.identity.application.rbac_engine import PermissionEvaluator
from app.identity.presentation import deps
from app.platform_core.errors.api_exceptions import ForbiddenError
from app.platform_core.security.token import TokenClaims


def require_permission(resource: str, action: str):
    async def _check(
        claims: TokenClaims = Depends(deps.get_current_user_claims),
        evaluator: PermissionEvaluator = Depends(deps.get_permission_evaluator),
    ) -> TokenClaims:
        await evaluator.assert_permission(
            user_id=claims.subject_user_id, org_id=claims.org_id, resource=resource, action=action
        )
        return claims

    return _check


def assert_path_org_matches_claims(org_id: str, claims: TokenClaims) -> UUID:
    """require_permission only checks that the caller holds a permission
    *somewhere* (against claims.org_id, from their own token) — it says
    nothing about whether the org_id in the URL path is that same
    organization. Every route keyed by a path org_id must call this too,
    or a permission holder in one org can act on any other org's data
    just by changing the URL. Mirrors ticket_system's identical helper."""
    parsed = UUID(org_id)
    if parsed != claims.org_id:
        raise ForbiddenError("Path organization does not match the authenticated user's organization")
    return parsed
