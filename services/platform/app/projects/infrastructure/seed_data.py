"""
This context's contribution to Identity's shared Permission Catalog — per
the extension point app.identity.infrastructure.seed_data documents
("each bounded context is expected to extend PERMISSION_CATALOG with its
own resource:action pairs"). app/main.py passes PROJECTS_PERMISSION_CATALOG
into IdentityModule.seed(extra_permissions=...) at startup; Identity never
imports this module.

Importing `PermissionSpec` here is a deliberate Shared Kernel exception
(DDD vocabulary), not a violation of the cross-context dependency rule —
it's a stateless, behaviorless data shape that exists specifically to be
reused this way, unlike importing an entity, repository, or UnitOfWork
would be (which is exactly what identity_adapter.py's Anti-Corruption
Layer exists to avoid doing directly).
"""

from __future__ import annotations

from app.identity.infrastructure.seed_data import PermissionSpec

PROJECTS_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("workspace", "create", "Create a workspace"),
    PermissionSpec("workspace", "read", "View workspace details"),
    PermissionSpec("workspace", "update", "Update workspace name/settings"),
    PermissionSpec("workspace", "archive", "Archive/reactivate a workspace"),
    PermissionSpec("workspace", "manage_members", "Add/remove workspace members"),
    PermissionSpec("project", "create", "Create a project"),
    PermissionSpec("project", "read", "View project details"),
    PermissionSpec("project", "update", "Update project name/description/status/visibility"),
    PermissionSpec("project", "archive", "Archive/unarchive a project"),
    PermissionSpec("project", "delete", "Delete a project"),
    PermissionSpec("project", "manage_members", "Invite/remove project members, change roles"),
    PermissionSpec("project_template", "create", "Create or import a project template"),
    PermissionSpec("project_template", "update", "Update or delete a project template"),
)
