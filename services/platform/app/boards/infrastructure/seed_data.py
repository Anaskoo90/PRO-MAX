"""
This context's contribution to Identity's shared Permission Catalog — same
extension point Projects & Workspaces and Tasks & Work Management already
use. app/main.py passes BOARDS_PERMISSION_CATALOG into
IdentityModule.seed(extra_permissions=...) at startup; Identity never
imports this module.

Importing `PermissionSpec` here is the same deliberate Shared Kernel
exception already established (see app.projects.infrastructure.seed_data
and app.tasks.infrastructure.seed_data) — a stateless, behaviorless data
shape, not a modification of or dependency on Identity's behavior.
"""

from __future__ import annotations

from app.identity.infrastructure.seed_data import PermissionSpec

BOARDS_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("board", "view", "View a board and its columns/cards"),
    PermissionSpec("board", "manage", "Create/update/archive/restore/delete boards, columns, and swimlanes"),
    PermissionSpec("board", "move_tasks", "Move tasks between columns, swimlanes, and the backlog"),
    PermissionSpec("board", "manage_sprint", "Create/start/complete/cancel sprints and manage sprint assignment"),
)
