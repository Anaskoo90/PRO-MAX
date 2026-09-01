"""
Anti-Corruption Layer: the only file in this bounded context permitted to
import Identity's application types. Translates Identity's
OrganizationManagementService.get() (which raises OrganizationNotFoundError)
into this context's own OrganizationLookupPort shape (a plain None on
"not found") so nothing above the infrastructure layer here ever sees an
Identity exception.

Constructed in composition.py with a reference to IdentityModule's own
public organization_management_service instance — same pattern as
projects/infrastructure/identity_adapter.py.
"""

from __future__ import annotations

from uuid import UUID

from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.exceptions import OrganizationNotFoundError


class IdentityOrganizationLookupAdapter:
    def __init__(self, organization_management_service: OrganizationManagementService) -> None:
        self._organization_management_service = organization_management_service

    async def get_org_name(self, *, org_id: UUID) -> str | None:
        try:
            org = await self._organization_management_service.get(org_id=org_id)
        except OrganizationNotFoundError:
            return None
        return org.name
