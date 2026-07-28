"""
This context's contribution to Identity's shared Permission Catalog — same
extension point Projects & Workspaces already uses. app/main.py passes
TASKS_PERMISSION_CATALOG into IdentityModule.seed(extra_permissions=...)
at startup, alongside PROJECTS_PERMISSION_CATALOG; Identity never imports
this module.
"""

from __future__ import annotations

from app.identity.infrastructure.seed_data import PermissionSpec

TASKS_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("task", "create", "Create a task"),
    PermissionSpec("task", "read", "View task details"),
    PermissionSpec("task", "update", "Update a task's title/description/status/priority/dates"),
    PermissionSpec("task", "delete", "Delete or archive/restore a task"),
    PermissionSpec("task", "manage_assignments", "Assign/reassign/unassign task members"),
    PermissionSpec("task", "manage_relationships", "Manage parent/subtask, dependency, and related-task links"),
    PermissionSpec("label", "manage", "Create/update/delete project labels"),
    PermissionSpec("workflow", "manage", "Create/update a project's task workflow definition"),
)
