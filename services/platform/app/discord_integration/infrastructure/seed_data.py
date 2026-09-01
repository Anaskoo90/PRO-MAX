"""
This context's contribution to Identity's shared Permission Catalog — same
extension point every other bounded context already uses. app/main.py
passes DISCORD_PERMISSION_CATALOG into IdentityModule.seed(extra_permissions=...)
at startup; Identity never imports this module.
"""

from __future__ import annotations

from app.identity.infrastructure.seed_data import PermissionSpec

DISCORD_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("discord", "manage_integration", "Link, configure, or unlink a Discord guild for the organization"),
)
