"""
Projects & Workspaces composition root.

Takes the already-constructed IdentityModule as a constructor dependency —
this is the one place cross-context wiring is allowed (the composition
root), and it's exactly how OrgPermissionCheckerPort/UserDirectoryPort get
their real implementations: Identity's own PermissionEvaluator instance
(structural match, no adapter needed) and IdentityUserDirectoryAdapter
(a real Anti-Corruption Layer) respectively.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.composition import IdentityModule
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.di.container import ServiceContainer
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.notifications.dispatcher import NotificationDispatcher
from app.projects.application.membership_management import ProjectMembershipService
from app.projects.application.project_management import ProjectService
from app.projects.application.template_management import ProjectTemplateService
from app.projects.application.workspace_management import WorkspaceService
from app.projects.infrastructure.identity_adapter import IdentityUserDirectoryAdapter
from app.projects.infrastructure.seed_data import PROJECTS_PERMISSION_CATALOG
from app.projects.infrastructure.unit_of_work import ProjectsUnitOfWork
from app.projects.presentation import deps, membership_router, projects_router, templates_router, workspaces_router


class ProjectsModule:
    module_name = "projects"

    def __init__(self, settings: PlatformSettings, identity_module: IdentityModule) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

        self.dispatcher = EventDispatcher()
        self.notification_dispatcher = NotificationDispatcher()

        def uow_factory() -> ProjectsUnitOfWork:
            return ProjectsUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # Cross-context wiring: Identity's PermissionEvaluator satisfies
        # OrgPermissionCheckerPort structurally, no adapter class needed.
        permission_checker = identity_module.permission_evaluator

        # Cross-context wiring: the Anti-Corruption Layer.
        user_directory = IdentityUserDirectoryAdapter(identity_module.create_unit_of_work)

        self.workspace_service = WorkspaceService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
        )
        self.project_service = ProjectService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
        )
        self.project_membership_service = ProjectMembershipService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, notification_dispatcher=self.notification_dispatcher,
            permission_checker=permission_checker, user_directory=user_directory,
        )
        self.project_template_service = ProjectTemplateService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
        )

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(WorkspaceService, self.workspace_service)
        container.register_instance(ProjectService, self.project_service)
        container.register_instance(ProjectMembershipService, self.project_membership_service)
        container.register_instance(ProjectTemplateService, self.project_template_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(workspaces_router.router)
        app.include_router(projects_router.router)
        app.include_router(membership_router.router)
        app.include_router(templates_router.router)

        app.dependency_overrides[deps.get_workspace_service] = lambda: self.workspace_service
        app.dependency_overrides[deps.get_project_service] = lambda: self.project_service
        app.dependency_overrides[deps.get_project_membership_service] = lambda: self.project_membership_service
        app.dependency_overrides[deps.get_project_template_service] = lambda: self.project_template_service


__all__ = ["ProjectsModule", "PROJECTS_PERMISSION_CATALOG"]
