"""
Ticket System composition root: wires domain/application/infrastructure/
presentation together and exposes the hooks app/main.py needs —
`register` (DI container), `mount` (FastAPI routers + dependency
overrides).

Phase 1A needed no new permissions (create/read/update already existed in
Identity's own catalog). Phase 1B adds TICKET_PERMISSION_CATALOG
(ticket:claim, ticket:manage_categories), since claim/transfer/category
management have no existing equivalent to reuse.

Takes IdentityModule and DiscordIntegrationModule as constructor
dependencies — the composition root is the one place cross-context wiring
is allowed. Reuses Identity's real PermissionEvaluator instance
(OrgPermissionCheckerPort, structural match, no adapter needed) and wraps
Discord Integration's DiscordSetupService with this context's own
DiscordIntegrationGuildResolverAdapter (an Anti-Corruption Layer, not a
modification of Discord Integration).
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.discord_integration.composition import DiscordIntegrationModule
from app.identity.composition import IdentityModule
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.di.container import ServiceContainer
from app.platform_core.events.dispatcher import EventDispatcher
from app.ticket_system.application.ticket_categories import TicketCategoryService
from app.ticket_system.application.ticket_lifecycle import TicketLifecycleService
from app.ticket_system.infrastructure.discord_integration_adapter import DiscordIntegrationGuildResolverAdapter
from app.ticket_system.infrastructure.seed_data import TICKET_PERMISSION_CATALOG
from app.ticket_system.infrastructure.unit_of_work import TicketUnitOfWork
from app.ticket_system.presentation import deps, ticket_bot_router, ticket_categories_router, tickets_router


class TicketSystemModule:
    module_name = "ticket_system"

    def __init__(
        self, settings: PlatformSettings, identity_module: IdentityModule,
        discord_integration_module: DiscordIntegrationModule,
    ) -> None:
        self._settings = settings
        engine = create_async_engine(str(settings.database_url))
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

        self.dispatcher = EventDispatcher()

        def uow_factory() -> TicketUnitOfWork:
            return TicketUnitOfWork(self._session_factory)

        self._uow_factory = uow_factory

        # --- Cross-context wiring (composition root only) ---
        permission_checker = identity_module.permission_evaluator
        guild_resolver = DiscordIntegrationGuildResolverAdapter(discord_integration_module.discord_setup_service)

        self.ticket_lifecycle_service = TicketLifecycleService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            guild_resolver=guild_resolver,
        )
        self.ticket_category_service = TicketCategoryService(
            uow_factory=uow_factory, dispatcher=self.dispatcher, permission_checker=permission_checker,
            guild_resolver=guild_resolver,
        )

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(TicketLifecycleService, self.ticket_lifecycle_service)
        container.register_instance(TicketCategoryService, self.ticket_category_service)

    def mount(self, app: FastAPI) -> None:
        app.include_router(tickets_router.router)
        app.include_router(ticket_categories_router.router)
        app.include_router(ticket_bot_router.router)

        app.dependency_overrides[deps.get_ticket_lifecycle_service] = lambda: self.ticket_lifecycle_service
        app.dependency_overrides[deps.get_ticket_category_service] = lambda: self.ticket_category_service


__all__ = ["TicketSystemModule", "TICKET_PERMISSION_CATALOG"]
