"""
Permission Catalog + System Roles seed data.

The catalog here covers Identity's own resources plus the cross-context
resource names already established in the Solution Design Pack's API
Specifications (ticket, invoice, ...); each bounded context is expected to
extend PERMISSION_CATALOG with its own resource:action pairs as it's
implemented, following the same (resource, action, description) shape —
not a closed list.

Run via scripts/seed-dev-data.sh (or the seed_identity() function directly)
against a fresh database — idempotent: existing rows (matched by resource+
action, or by name for roles) are left untouched, not duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.domain.rbac import Permission, Role
from app.identity.infrastructure.unit_of_work import IdentityUnitOfWork


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    resource: str
    action: str
    description: str


PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("organization", "read", "View organization details"),
    PermissionSpec("organization", "update", "Update organization name/settings"),
    PermissionSpec("organization", "manage_ownership", "Transfer organization ownership"),
    PermissionSpec("organization", "manage_status", "Suspend/reactivate the organization"),
    PermissionSpec("team", "create", "Create a team"),
    PermissionSpec("team", "update", "Update a team"),
    PermissionSpec("team", "delete", "Delete a team"),
    PermissionSpec("team", "manage_members", "Add/remove team members"),
    PermissionSpec("role", "create", "Create a custom role"),
    PermissionSpec("role", "update", "Update a custom role"),
    PermissionSpec("role", "delete", "Delete a custom role"),
    PermissionSpec("role", "assign", "Assign a role to a user"),
    PermissionSpec("permission", "assign", "Assign a permission to a role"),
    PermissionSpec("user", "read", "View user profiles in the organization"),
    PermissionSpec("user", "manage_status", "Suspend/reactivate a user account"),
    PermissionSpec("audit_log", "read", "View organization audit logs"),
    PermissionSpec("ticket", "create", "Create a ticket"),
    PermissionSpec("ticket", "read", "View tickets"),
    PermissionSpec("ticket", "update", "Update a ticket"),
    PermissionSpec("invoice", "read", "View invoices"),
    PermissionSpec("invoice", "manage", "Create/void invoices"),
)

# Baseline "member" grants — deliberately NOT auto-extended by other
# bounded contexts' extra_permissions (see seed_identity): a plain member
# shouldn't silently gain new capabilities just because another context
# grew the catalog. org_owner/org_admin *are* auto-extended, since "full
# control over the organization" should mean full control, including over
# resources contexts other than Identity introduce later.
_MEMBER_BASELINE_PERMISSION_KEYS: tuple[tuple[str, str], ...] = (
    ("organization", "read"),
    ("team", "manage_members"),
    ("user", "read"),
    ("ticket", "create"),
    ("ticket", "read"),
    ("ticket", "update"),
)


async def seed_identity(
    uow: IdentityUnitOfWork, *, extra_permissions: tuple[PermissionSpec, ...] = ()
) -> None:
    """
    Idempotent. `extra_permissions` is the extension point other bounded
    contexts use to register their own resource:action pairs into the same
    Identity-owned permissions table (e.g. Projects & Workspaces passing
    PROJECTS_PERMISSION_CATALOG) — Identity never imports another
    context's module to know what these are, it just receives plain
    PermissionSpec tuples from the composition root at startup.
    """
    full_catalog = (*PERMISSION_CATALOG, *extra_permissions)

    existing_permissions = {(p.resource, p.action): p for p in await uow.permissions.list_all()}
    for spec in full_catalog:
        if (spec.resource, spec.action) not in existing_permissions:
            permission = Permission.create(resource=spec.resource, action=spec.action, description=spec.description)
            await uow.permissions.add(permission)
            existing_permissions[(spec.resource, spec.action)] = permission

    system_roles: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
        "org_owner": (
            "Full control over the organization, including ownership transfer",
            tuple((p.resource, p.action) for p in full_catalog),
        ),
        "org_admin": (
            "Administrative control excluding ownership transfer",
            tuple((p.resource, p.action) for p in full_catalog if p.action != "manage_ownership"),
        ),
        "member": ("Baseline organization member", _MEMBER_BASELINE_PERMISSION_KEYS),
    }

    for role_name, (description, permission_keys) in system_roles.items():
        role = await uow.roles.get_by_name(None, role_name)
        if role is None:
            role = Role.create_system_role(name=role_name, description=description)
            await uow.roles.add(role)
        for key in permission_keys:
            permission = existing_permissions[key]
            # grant_permission_during_bootstrap, not grant_permission: system
            # roles are immutable through the public API (Role._assert_mutable
            # still enforces that everywhere else), but the seed process is the
            # one trusted place allowed to establish and grow their permission
            # sets as the catalog grows across bounded contexts. Guarded so a
            # repeat idempotent seed run doesn't re-fire PermissionAssignedToRole
            # for grants the role already has.
            if permission.id not in role.permission_ids:
                role.grant_permission_during_bootstrap(permission.id)
        await uow.roles.update(role)

    await uow.commit()
