"""
Shared FastAPI dependencies for the Projects & Workspaces presentation
layer.

Authentication is *not* reimplemented here — `get_current_user_claims` is
imported directly from app.identity.presentation.deps. Both contexts sit
behind the same FastAPI app and the same JwtTokenService instance
(IdentityModule.mount already wires the override once, application-wide),
so re-deriving JWT verification in this context would be pure duplication.
This is presentation-layer reuse of a stateless dependency function, not a
domain/infrastructure coupling — the two are treated differently on
purpose (see application/ports.py's docstring).
"""

from __future__ import annotations

from app.identity.presentation.deps import get_current_user_claims  # noqa: F401  (re-exported for routers)
from app.projects.application.membership_management import ProjectMembershipService
from app.projects.application.project_management import ProjectService
from app.projects.application.template_management import ProjectTemplateService
from app.projects.application.workspace_management import WorkspaceService


def get_workspace_service() -> WorkspaceService:
    raise NotImplementedError("WorkspaceService dependency not wired")


def get_project_service() -> ProjectService:
    raise NotImplementedError("ProjectService dependency not wired")


def get_project_membership_service() -> ProjectMembershipService:
    raise NotImplementedError("ProjectMembershipService dependency not wired")


def get_project_template_service() -> ProjectTemplateService:
    raise NotImplementedError("ProjectTemplateService dependency not wired")
