"""
Discord Integration composition root: wires domain/application/
infrastructure/presentation together and exposes the hooks app/main.py
needs — `register` (DI container), `mount` (FastAPI routers + dependency
overrides). No `seed` hook of its own beyond contributing
DISCORD_PERMISSION_CATALOG into IdentityModule.seed(extra_permissions=...),
same pattern as every prior context.

Takes IdentityModule as a constructor dependency — the composition root is
the one place cross-context wiring is allowed. Reuses Identity's real
PermissionEvaluator instance (OrgPermissionCheckerPort, structural match,
no adapter needed) and wraps Identity's OrganizationManagementService with
this context's own IdentityOrganizationLookupAdapter (an Anti-Corruption
Layer, not a modification of Identity).
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.composition import IdentityModule
from app.platform_core.di.container import ServiceContainer
from app.platform_core.events.dispatcher import EventDispatcher
from app.discord_integration.application.discord_setup import DiscordSetupService
from app.discord_integration.infrastructure.identity_adapter import IdentityOrganizationLookupAdapter
from app.discord_integration.infrastructure.seed_data import DISCORD_PERMISSION_CATALOG
from app.discord_integration.infrastructure.unit_of_work import DiscordIntegrationUnitOfWork
from app.discord_integration.presentation import bot_router, deps, setup_router
from app.discord_integration.settings import DiscordIntegrationSettings


class DiscordIntegrationModule:
    module_name = "discord_integration"

    def __init__(self, settings: DiscordIntegrationSettings, identity_module: IdentityModule) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

        self.dispatcher = EventDispatcher()

        def uow_factory() -> DiscordIntegrationUnitOfWork:
            return DiscordIntegrationUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # --- Cross-context wiring (composition root only) ---
        permission_checker = identity_module.permission_evaluator
        organization_lookup = IdentityOrganizationLookupAdapter(identity_module.organization_management_service)

        self.discord_setup_service = DiscordSetupService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            organization_lookup=organization_lookup, discord_application_id=settings.discord_application_id,
        )

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(DiscordSetupService, self.discord_setup_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(setup_router.router)
        app.include_router(bot_router.router)

        app.dependency_overrides[deps.get_discord_setup_service] = lambda: self.discord_setup_service
        app.dependency_overrides[deps.get_bot_service_secret] = lambda: self._settings.discord_bot_service_secret


__all__ = ["DiscordIntegrationModule", "DISCORD_PERMISSION_CATALOG"]
