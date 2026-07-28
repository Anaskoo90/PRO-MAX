"""
This context's contribution to Identity's shared Permission Catalog — same
extension point every prior context already uses. app/main.py passes
WORKFLOW_PERMISSION_CATALOG into IdentityModule.seed(extra_permissions=...)
at startup; Identity never imports this module.

Importing `PermissionSpec` here is the same deliberate Shared Kernel
exception already established (see app.boards.infrastructure.seed_data and
every prior context's own seed_data.py) — a stateless, behaviorless data
shape, not a modification of or dependency on Identity's behavior.
"""

from __future__ import annotations

from app.identity.infrastructure.seed_data import PermissionSpec

WORKFLOW_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("workflow", "view", "View a workflow, its states, and transitions"),
    PermissionSpec("workflow", "manage", "Create/update/archive/restore/delete workflows, states, and transitions"),
    PermissionSpec("workflow", "execute", "Execute a transition on a task enrolled in a workflow"),
    PermissionSpec("workflow", "manage_automation", "Configure and cancel scheduled/delayed workflow actions"),
)
