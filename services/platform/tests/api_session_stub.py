"""Session-bound access tokens for database-free API routing tests.

The API smoke tests exercise authentication ordering and tenant/path guards
without starting the application lifespan or a database.  They therefore
use this explicit test double for the persisted-session check.  The real
session validator is covered separately by identity unit and integration
tests.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.identity.presentation import deps as identity_deps
from app.platform_core.shared_kernel.utils import new_uuid7


class _ActiveAccessSessionAuthenticationService:
    async def is_access_session_active(self, **_kwargs) -> bool:
        return True


@contextmanager
def allow_active_test_sessions(app):
    dependency = identity_deps.get_authentication_service
    previous = app.dependency_overrides.get(dependency)
    service = _ActiveAccessSessionAuthenticationService()
    app.dependency_overrides[dependency] = lambda: service
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = previous


def issue_session_bound_test_token(
    token_service,
    *,
    user_id,
    org_id,
) -> str:
    return token_service.issue_access_token(
        user_id=user_id,
        org_id=org_id,
        scopes=[],
        session_id=new_uuid7(),
    )
