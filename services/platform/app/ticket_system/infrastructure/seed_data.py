"""
This context's contribution to Identity's shared Permission Catalog — same
extension point every other bounded context already uses. app/main.py
passes TICKET_PERMISSION_CATALOG into IdentityModule.seed(extra_permissions=...)
at startup; Identity never imports this module.

Phase 1A needed no new permissions (create/read/update already existed in
Identity's own catalog). Phase 1B introduces claim/transfer/category
management, which don't have an existing equivalent to reuse.
"""

from __future__ import annotations

from app.identity.infrastructure.seed_data import PermissionSpec

TICKET_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("ticket", "claim", "Claim, unclaim, or transfer a ticket"),
    PermissionSpec("ticket", "manage_categories", "Create, update, or deactivate ticket categories"),
)
