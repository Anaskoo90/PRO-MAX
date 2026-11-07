"""The one place that decides "may this organization's members act right now?".

Used by authentication (login, MFA completion, refresh, access tokens) and by
invitation acceptance, so they cannot drift apart.
"""

from __future__ import annotations

from app.identity.domain.exceptions import OrganizationNotActiveError
from app.platform_core.shared_kernel.types import OrgId


async def assert_organization_active(uow, org_id: OrgId, *, lock: bool) -> None:
    """Raise OrganizationNotActiveError unless the organization exists and is ACTIVE.

    Fails closed: an organization that can't be found counts as inactive.

    `lock=True` takes a shared lock on the organization row (`FOR SHARE`)
    BEFORE the caller writes any user/session row, so the caller's transaction
    serializes against OrganizationManagementService suspending or
    deactivating the organization (which holds `FOR UPDATE` and then revokes
    every session): either the caller's writes are committed before the status
    change is granted its lock (and, for sessions, are then revoked), or the
    caller waits and sees the new status. Shared locks don't block one another,
    so ordinary traffic is unaffected. The organization row is always locked
    FIRST, the same order every other organization-level operation uses.

    `lock=False` is a plain read, for per-request access-token validation.
    """
    org = await (
        uow.organizations.get_by_id_for_share(org_id) if lock else uow.organizations.get_by_id(org_id)
    )
    if org is None or not org.is_active():
        raise OrganizationNotActiveError(org.status.value if org is not None else "missing")
