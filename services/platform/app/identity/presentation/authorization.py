"""Authorization Middleware: FastAPI dependency factory enforcing RBAC
permissions on a route. Usage:

    @router.post("/teams", dependencies=[Depends(require_permission("team", "create"))])
"""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.rbac_engine import PermissionEvaluator
from app.identity.presentation import deps
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
